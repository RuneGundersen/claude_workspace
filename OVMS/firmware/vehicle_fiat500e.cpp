/*
;    Project:       Open Vehicle Monitor System
;    Date:          5th July 2018
;    Modified:      2026 — UDS polling expanded (VCM + BMS + charger)
;
;    Changes:
;    1.0  Initial release
;    1.1  Add BPCM UDS polling via OVMS poll infrastructure.
;         Per-cell voltages published as v.b.c.voltage[0..95] → MQTT.
;         Shell commands: xse cells / xse scan <start> <end>
;    1.2  Add VCM driving data, BMS battery data, charger data polling.
;         New metrics: motor RPM/torque, speed, SOC, temps, currents.
;    1.3  Add TPMS (4 tire pressures via CAN-B UDS), key/ignition state,
;         and brake pedal.
;         New metrics: v.tp.fl/fr/rl/rr.p (kPa), v.e.on, v.e.footbrake.
;
;    (C) 2021       Guenther Huck
;    (C) 2011       Michael Stegen / Stegen Electronics
;    (C) 2011-2018  Mark Webb-Johnson
;    (C) 2011        Sonny Chen @ EPRO/DX
;
; Permission is hereby granted, free of charge, to any person obtaining a copy
; of this software and associated documentation files (the "Software"), to deal
; in the Software without restriction, including without limitation the rights
; to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
; copies of the Software, and to permit persons to whom the Software is
; furnished to do so, subject to the following conditions:
;
; The above copyright notice and this permission notice shall be included in
; all copies or substantial portions of the Software.
;
; THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
; IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
; FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE

; CAN bus layout:
;   CAN1  C-CAN  500 kbps  — powertrain / BMS (29-bit UDS)
;   CAN2  B-CAN   50 kbps  — body / comfort
;
; UDS ECU addresses (ISO 15765-2, 29-bit extended IDs):
;   VCM  0x42  TX 0x18DA42F1  RX 0x18DAF142  (motor / inverter / speed)
;   BMS  0x44  TX 0x18DA44F1  RX 0x18DAF144  (battery state)
;   OBC  0x47  TX 0x18DA47F1  RX 0x18DAF147  (on-board charger)
;
; Cell voltage DID:
;   Set via config:  config set xse bpcm.cell_did <hex-DID>
;   Default 0x0000 → disabled until discovered via "xse scan" command.
;
; MQTT metrics added (UDS-sourced):
;   v.b.c.voltage[0..95]   — cell voltages (V)
;   xse.b.cell_did         — active cell DID (informational)
;   xse.b.cell_count       — cells decoded in last reply
;   xse.v.m.torque         — motor torque (Nm)
;   xse.v.m.torque.tgt     — motor torque target (Nm)
;   xse.v.m.coolant.temp   — motor coolant temperature (°C)
*/

#include "ovms_log.h"
static const char *TAG = "v-fiat500e";

#include <stdio.h>
#include <string.h>
#include "vehicle_fiat500e.h"
#include "metrics_standard.h"
#include "ovms_metrics.h"
#include "ovms_config.h"
#include "ovms_command.h"


// ── Dynamic UDS poll table ───────────────────────────────────────────────────
// Built at startup by BuildPollTable().
// polltime[] = {state0, state1, state2, state3}  (seconds; 0 = skip)
//   state 0 = standby/off
//   state 1 = on / driving
//   state 2 = charging
//   state 3 = (reserved)

static OvmsPoller::poll_pid_t bpcm_polls_dyn[FT5E_POLL_MAX];


// ── Constructor ────────────────────────────────────────────────────────────

OvmsVehicleFiat500e::OvmsVehicleFiat500e()
  {
  ESP_LOGI(TAG, "Start Fiat 500e vehicle module (with cell-voltage polling)");

  // ── Existing metrics ─────────────────────────────────────────────────────
  ft_v_acelec_pwr  = MyMetrics.InitFloat("xse.v.b.acelec.pwr",  SM_STALE_MID, 0, Watts);
  ft_v_htrelec_pwr = MyMetrics.InitFloat("xse.v.b.htrelec.pwr", SM_STALE_MID, 0, Watts);

  // ── BMS cell voltage metrics ──────────────────────────────────────────────
  BmsSetCellDefaultThresholdsVoltage(0.050f, 0.100f);  // 50 mV warn, 100 mV alert
  BmsSetCellArrangementVoltage(FT5E_CELL_COUNT, 1);    // 96 cells, 1 per module
  MyMetrics.InitInt("xse.b.cell_did",   SM_STALE_HIGH, 0);
  MyMetrics.InitInt("xse.b.cell_count", SM_STALE_HIGH, 0);

  // ── VCM / motor metrics ───────────────────────────────────────────────────
  xse_v_m_torque       = MyMetrics.InitFloat("xse.v.m.torque",       SM_STALE_MID, 0, Nm);
  xse_v_m_torque_tgt   = MyMetrics.InitFloat("xse.v.m.torque.tgt",   SM_STALE_MID, 0, Nm);
  xse_v_m_coolant_temp = MyMetrics.InitFloat("xse.v.m.coolant.temp", SM_STALE_MID, 0, Celcius);

  // ── Cell DID from config ──────────────────────────────────────────────────
  m_cell_did = (uint16_t) MyConfig.GetParamValueInt("xse", "bpcm.cell_did", 0);
  m_cell_count = 0;
  ESP_LOGI(TAG, "Cell DID from config: 0x%04X%s",
           m_cell_did, m_cell_did ? "" : "  (disabled — run 'xse scan' to discover)");

  // ── Build dynamic poll table ──────────────────────────────────────────────
  BuildPollTable();

  // ── CAN buses ─────────────────────────────────────────────────────────────
  RegisterCanBus(1, CAN_MODE_ACTIVE, CAN_SPEED_500KBPS);
  RegisterCanBus(2, CAN_MODE_ACTIVE, CAN_SPEED_50KBPS);

  // ── UDS polling ───────────────────────────────────────────────────────────
  PollSetPidList(m_can1, bpcm_polls_dyn);
  PollSetState(0);

  // ── Scan state init ───────────────────────────────────────────────────────
  m_scan_active  = false;
  m_scan_did     = 0;
  m_scan_did_end = 0;
  m_scan_writer  = nullptr;

  // ── Shell commands ────────────────────────────────────────────────────────
  OvmsCommand *cmd_xse = MyCommandApp.RegisterCommand("xse", "Fiat 500e commands");

  cmd_xse->RegisterCommand("cells",
    "Show latest cell voltages",
    xse_cells, "", 0, 0);

  cmd_xse->RegisterCommand("scan",
    "Scan BPCM DIDs for cell data\n"
    "  xse scan <start_hex> <end_hex>   — probe DID range\n"
    "  xse scan auto                    — try known Bosch BMS DIDs\n"
    "  xse scan stop                    — abort scan",
    xse_scan, "<start|auto|stop> [end]", 1, 2);
  }

OvmsVehicleFiat500e::~OvmsVehicleFiat500e()
  {
  ESP_LOGI(TAG, "Stop Fiat 500e vehicle module");
  MyCommandApp.UnregisterCommand("xse");
  }


// ── Poll state management ──────────────────────────────────────────────────

void OvmsVehicleFiat500e::UpdatePollState()
  {
  // state 0 = off/standby  (slow / no polling)
  // state 1 = on / driving  (30 s)
  // state 2 = charging      (60 s)
  if (StandardMetrics.ms_v_charge_inprogress->AsBool())
    PollSetState(2);
  else if (StandardMetrics.ms_v_env_on->AsBool())
    PollSetState(1);
  else
    PollSetState(0);
  }


// ── Build UDS poll table ───────────────────────────────────────────────────

void OvmsVehicleFiat500e::BuildPollTable()
  {
  int n = 0;

  // ── VCM (ECU 0x42) — pack + driving data ───────────────────────────────
  // DID 0x2001: legacy pack status (log only)
  bpcm_polls_dyn[n++] = { FT5E_VCM_TXID, FT5E_VCM_RXID, VEHICLE_POLL_TYPE_READDATA,
                           0x2001, {0, 30, 60, 0}, 1, ISOTP_STD };
  // DID 0x203F: accelerator pedal position → ms_v_env_throttle
  bpcm_polls_dyn[n++] = { FT5E_VCM_TXID, FT5E_VCM_RXID, VEHICLE_POLL_TYPE_READDATA,
                           0x203F, {0, 5, 0, 0}, 1, ISOTP_STD };
  // DID 0x2098: motor shaft RPM → ms_v_mot_rpm
  bpcm_polls_dyn[n++] = { FT5E_VCM_TXID, FT5E_VCM_RXID, VEHICLE_POLL_TYPE_READDATA,
                           0x2098, {0, 5, 0, 0}, 1, ISOTP_STD };
  // DID 0x2090: motor torque → xse_v_m_torque
  bpcm_polls_dyn[n++] = { FT5E_VCM_TXID, FT5E_VCM_RXID, VEHICLE_POLL_TYPE_READDATA,
                           0x2090, {0, 5, 0, 0}, 1, ISOTP_STD };
  // DID 0x2094: torque target → xse_v_m_torque_tgt
  bpcm_polls_dyn[n++] = { FT5E_VCM_TXID, FT5E_VCM_RXID, VEHICLE_POLL_TYPE_READDATA,
                           0x2094, {0, 5, 0, 0}, 1, ISOTP_STD };
  // DID 0x204F: vehicle speed → ms_v_pos_speed
  bpcm_polls_dyn[n++] = { FT5E_VCM_TXID, FT5E_VCM_RXID, VEHICLE_POLL_TYPE_READDATA,
                           0x204F, {0, 5, 0, 0}, 1, ISOTP_STD };
  // DID 0x2063: HV pack voltage → ms_v_bat_voltage
  bpcm_polls_dyn[n++] = { FT5E_VCM_TXID, FT5E_VCM_RXID, VEHICLE_POLL_TYPE_READDATA,
                           0x2063, {0, 30, 60, 0}, 1, ISOTP_STD };
  // DID 0x200B: motor coolant temperature → xse_v_m_coolant_temp
  bpcm_polls_dyn[n++] = { FT5E_VCM_TXID, FT5E_VCM_RXID, VEHICLE_POLL_TYPE_READDATA,
                           0x200B, {0, 30, 0, 0}, 1, ISOTP_STD };

  // ── BMS (ECU 0x44) — battery state ──────────────────────────────────────
  // DID 0xA010: state of charge → ms_v_bat_soc
  bpcm_polls_dyn[n++] = { FT5E_BMS_TXID, FT5E_BMS_RXID, VEHICLE_POLL_TYPE_READDATA,
                           0xA010, {0, 30, 60, 0}, 1, ISOTP_STD };
  // DID 0xA608: pack temperature → ms_v_bat_temp
  bpcm_polls_dyn[n++] = { FT5E_BMS_TXID, FT5E_BMS_RXID, VEHICLE_POLL_TYPE_READDATA,
                           0xA608, {0, 30, 60, 0}, 1, ISOTP_STD };
  // DID 0xA012: battery current → ms_v_bat_current
  bpcm_polls_dyn[n++] = { FT5E_BMS_TXID, FT5E_BMS_RXID, VEHICLE_POLL_TYPE_READDATA,
                           0xA012, {0, 10, 30, 0}, 1, ISOTP_STD };
  // DID 0xA042: 12 V auxiliary voltage → ms_v_bat_12v_voltage
  bpcm_polls_dyn[n++] = { FT5E_BMS_TXID, FT5E_BMS_RXID, VEHICLE_POLL_TYPE_READDATA,
                           0xA042, {0, 60, 60, 0}, 1, ISOTP_STD };

  // ── OBC (ECU 0x47) — on-board charger ───────────────────────────────────
  // DID 0x010A: AC charge current → ms_v_charge_current
  bpcm_polls_dyn[n++] = { FT5E_OBC_TXID, FT5E_OBC_RXID, VEHICLE_POLL_TYPE_READDATA,
                           0x010A, {0, 0, 30, 0}, 1, ISOTP_STD };

  // ── VCM — ignition/key state ─────────────────────────────────────────────
  // DID 0x0303: 01 = key on/ready, 00 = off → ms_v_env_on
  // Polled in all states so PollState transitions correctly when car wakes up.
  bpcm_polls_dyn[n++] = { FT5E_VCM_TXID, FT5E_VCM_RXID, VEHICLE_POLL_TYPE_READDATA,
                           0x0303, {30, 5, 30, 0}, 1, ISOTP_STD };

  // ── TPMS (ECU 0xA1, CAN2/B-CAN 50 kbps) ─────────────────────────────────
  // DIDs 0x40A1–0x40A4: tire pressures, raw uint16 / 10 = kPa, pollbus=2
  bpcm_polls_dyn[n++] = { FT5E_TPMS_TXID, FT5E_TPMS_RXID, VEHICLE_POLL_TYPE_READDATA,
                           FT5E_TPMS_DID_FL, {0, 60, 0, 0}, 2, ISOTP_STD };
  bpcm_polls_dyn[n++] = { FT5E_TPMS_TXID, FT5E_TPMS_RXID, VEHICLE_POLL_TYPE_READDATA,
                           FT5E_TPMS_DID_FR, {0, 60, 0, 0}, 2, ISOTP_STD };
  bpcm_polls_dyn[n++] = { FT5E_TPMS_TXID, FT5E_TPMS_RXID, VEHICLE_POLL_TYPE_READDATA,
                           FT5E_TPMS_DID_RL, {0, 60, 0, 0}, 2, ISOTP_STD };
  bpcm_polls_dyn[n++] = { FT5E_TPMS_TXID, FT5E_TPMS_RXID, VEHICLE_POLL_TYPE_READDATA,
                           FT5E_TPMS_DID_RR, {0, 60, 0, 0}, 2, ISOTP_STD };

  // ── Optional cell voltage DID (from config) ──────────────────────────────
  if (m_cell_did != 0) {
    bpcm_polls_dyn[n++] = { FT5E_VCM_TXID, FT5E_VCM_RXID, VEHICLE_POLL_TYPE_READDATA,
                             m_cell_did, {0, 30, 60, 0}, 1, ISOTP_STD };
  }

  // End-of-list marker
  bpcm_polls_dyn[n] = POLL_LIST_END;

  ESP_LOGI(TAG, "Poll table built: %d entries (cell DID %s)",
           n, m_cell_did ? "enabled" : "disabled");
  }


// ── Ticker (1 Hz) ─────────────────────────────────────────────────────────

void OvmsVehicleFiat500e::Ticker1(uint32_t ticker)
  {
  UpdatePollState();

  // DID scan: send one UDS request per second
  if (m_scan_active) {
    if (m_scan_did > m_scan_did_end) {
      // Scan complete
      m_scan_active = false;
      if (m_scan_writer) {
        m_scan_writer->printf("Scan complete (0x%04X–0x%04X).\n"
          "If any DID returned ≥192 bytes with values 2500–4200,"
          " that is the cell voltage DID.\n"
          "Set it with:  config set xse bpcm.cell_did <DID>\n"
          "Then restart the module to activate polling.\n",
          (uint16_t)(m_scan_did_end - (m_scan_did - m_scan_did_end)),
          m_scan_did_end);
        m_scan_writer = nullptr;
      }
      return;
    }

    if (m_scan_writer)
      m_scan_writer->printf("→ DID 0x%04X ...\n", m_scan_did);

    SendBpcmRequest(m_scan_did);
    m_scan_did++;
  }
  }


// ── Send a raw UDS ReadDataByIdentifier (service 0x22) to BPCM ────────────

void OvmsVehicleFiat500e::SendBpcmRequest(uint16_t did)
  {
  CAN_frame_t frame = {};
  frame.FIR.B.FF  = CAN_frame_ext;   // 29-bit extended ID
  frame.MsgID     = FT5E_BPCM_TXID;
  frame.FIR.B.DLC = 8;
  frame.data.u8[0] = 0x03;            // PCI: single frame, 3 data bytes
  frame.data.u8[1] = 0x22;            // UDS service: ReadDataByIdentifier
  frame.data.u8[2] = (did >> 8) & 0xFF;
  frame.data.u8[3] = did & 0xFF;
  frame.data.u8[4] = 0x00;
  frame.data.u8[5] = 0x00;
  frame.data.u8[6] = 0x00;
  frame.data.u8[7] = 0x00;
  m_can1->Write(&frame);
  }


// ── UDS poll reply handler ─────────────────────────────────────────────────

void OvmsVehicleFiat500e::IncomingPollReply(const OvmsPoller::poll_job_t &job,
                                             uint8_t* data, uint8_t length)
  {
  uint16_t pid = job.pid;
  switch (pid) {

    // ── DID 0x2001: VCM pack status (log only) ──────────────────────────────
    case 0x2001:
      ESP_LOGD(TAG, "VCM DID 0x2001 (%u bytes):", length);
      for (int i = 0; i < length && i < 64; i += 8) {
        ESP_LOGD(TAG, "  [%02d] %02X %02X %02X %02X  %02X %02X %02X %02X", i,
          (i+0 < length ? data[i+0] : 0), (i+1 < length ? data[i+1] : 0),
          (i+2 < length ? data[i+2] : 0), (i+3 < length ? data[i+3] : 0),
          (i+4 < length ? data[i+4] : 0), (i+5 < length ? data[i+5] : 0),
          (i+6 < length ? data[i+6] : 0), (i+7 < length ? data[i+7] : 0));
      }
      if (m_scan_active && m_scan_writer) {
        m_scan_writer->printf("  DID 0x2001 → %u bytes", length);
        for (int i = 0; i < length && i < 32; i++)
          m_scan_writer->printf(" %02X", data[i]);
        if (length > 32) m_scan_writer->printf(" ...");
        m_scan_writer->printf("\n");
      }
      break;

    // ── VCM driving data ─────────────────────────────────────────────────────

    // DID 0x203F: accelerator pedal position (0–100 %)
    case 0x203F:
      if (length >= 1)
        StandardMetrics.ms_v_env_throttle->SetValue((float)data[0] / 255.0f * 100.0f);
      break;

    // DID 0x2098: motor shaft speed (raw - 32767 = RPM)
    case 0x2098:
      if (length >= 2) {
        int16_t rpm = (int16_t)(((uint16_t)data[0] << 8) | data[1]) - 32767;
        StandardMetrics.ms_v_mot_rpm->SetValue(rpm);
      }
      break;

    // DID 0x2090: motor torque (raw - 1023 = Nm)
    case 0x2090:
      if (length >= 2)
        xse_v_m_torque->SetValue((float)((int16_t)(((uint16_t)data[0] << 8) | data[1]) - 1023));
      break;

    // DID 0x2094: motor torque target (raw - 1023 = Nm)
    case 0x2094:
      if (length >= 2)
        xse_v_m_torque_tgt->SetValue((float)((int16_t)(((uint16_t)data[0] << 8) | data[1]) - 1023));
      break;

    // DID 0x204F: vehicle speed (raw / 10 = km/h)
    case 0x204F:
      if (length >= 2)
        StandardMetrics.ms_v_pos_speed->SetValue(
          (float)(((uint16_t)data[0] << 8) | data[1]) / 10.0f);
      break;

    // DID 0x2063: HV pack voltage (raw = V)
    case 0x2063:
      if (length >= 2)
        StandardMetrics.ms_v_bat_voltage->SetValue(
          (float)(((uint16_t)data[0] << 8) | data[1]));
      break;

    // DID 0x200B: motor coolant temperature (data[2] - 40 = °C)
    case 0x200B:
      if (length >= 3)
        xse_v_m_coolant_temp->SetValue((float)data[2] - 40.0f);
      break;

    // ── BMS battery data ──────────────────────────────────────────────────────

    // DID 0xA010: state of charge (raw / 255 * 100 = %)
    case 0xA010:
      if (length >= 1)
        StandardMetrics.ms_v_bat_soc->SetValue((float)data[0] / 255.0f * 100.0f);
      break;

    // DID 0xA608: pack temperature (raw - 50 = °C)
    case 0xA608:
      if (length >= 1)
        StandardMetrics.ms_v_bat_temp->SetValue((float)data[0] - 50.0f);
      break;

    // DID 0xA012: battery current (raw / 20 = A)
    case 0xA012:
      if (length >= 2)
        StandardMetrics.ms_v_bat_current->SetValue(
          (float)(((uint16_t)data[0] << 8) | data[1]) / 20.0f);
      break;

    // DID 0xA042: 12 V auxiliary voltage (raw / 1000 = V)
    case 0xA042:
      if (length >= 2)
        StandardMetrics.ms_v_bat_12v_voltage->SetValue(
          (float)(((uint16_t)data[0] << 8) | data[1]) / 1000.0f);
      break;

    // ── VCM key/ignition state ────────────────────────────────────────────────

    // DID 0x0303: key state (01 = on/ready, 00 = off) → ms_v_env_on
    case 0x0303:
      if (length >= 1)
        StandardMetrics.ms_v_env_on->SetValue(data[0] != 0);
      break;

    // ── TPMS tire pressures (CAN-B, ECU 0xA1) ────────────────────────────────
    // raw uint16 big-endian / 10 = kPa

    // ms_v_tpms_pressure is OvmsMetricVector<float>[0..3] = FL, FR, RL, RR in kPa

    case FT5E_TPMS_DID_FL:  // 0x40A1 front-left  → index 0
      if (length >= 2)
        StandardMetrics.ms_v_tpms_pressure->SetElemValue(
          0, (float)(((uint16_t)data[0] << 8) | data[1]) / 10.0f, kPa);
      break;

    case FT5E_TPMS_DID_FR:  // 0x40A2 front-right → index 1
      if (length >= 2)
        StandardMetrics.ms_v_tpms_pressure->SetElemValue(
          1, (float)(((uint16_t)data[0] << 8) | data[1]) / 10.0f, kPa);
      break;

    case FT5E_TPMS_DID_RL:  // 0x40A3 rear-left   → index 2
      if (length >= 2)
        StandardMetrics.ms_v_tpms_pressure->SetElemValue(
          2, (float)(((uint16_t)data[0] << 8) | data[1]) / 10.0f, kPa);
      break;

    case FT5E_TPMS_DID_RR:  // 0x40A4 rear-right  → index 3
      if (length >= 2)
        StandardMetrics.ms_v_tpms_pressure->SetElemValue(
          3, (float)(((uint16_t)data[0] << 8) | data[1]) / 10.0f, kPa);
      break;

    // ── OBC charger data ──────────────────────────────────────────────────────

    // DID 0x010A: AC charge current (raw / 10 - 50 = A)
    case 0x010A:
      if (length >= 2)
        StandardMetrics.ms_v_charge_current->SetValue(
          (float)(((uint16_t)data[0] << 8) | data[1]) / 10.0f - 50.0f);
      break;

    // ── Configured cell voltage DID ──────────────────────────────────────────
    default:
      if (pid == m_cell_did && m_cell_did != 0) {
        DecodeCellVoltages(pid, data, length);
      } else if (m_scan_active && m_scan_writer) {
        // Scan result from a non-standard DID
        m_scan_writer->printf("  DID 0x%04X → %u bytes", pid, length);
        for (int i = 0; i < length && i < 32; i++)
          m_scan_writer->printf(" %02X", data[i]);
        if (length > 32) m_scan_writer->printf(" ...");
        m_scan_writer->printf("\n");
      }
      break;
  }
  }


// ── Decode cell voltages from UDS reply payload ────────────────────────────
//
// Most Bosch BMS implementations encode cells as big-endian uint16 millivolts.
// 96 cells × 2 bytes = 192 bytes minimum.
// Valid range: 2000–4500 mV (2.0–4.5 V).
//
// If your BMS uses a different encoding (e.g. 10-bit packed, 1/100 V units),
// adjust the formula below and set FT5E_CELL_MV_SCALE accordingly.

#define FT5E_CELL_MV_SCALE  1       // millivolts per LSB
#define FT5E_CELL_MV_MIN    2000    // reject values below this
#define FT5E_CELL_MV_MAX    4500    // reject values above this

void OvmsVehicleFiat500e::DecodeCellVoltages(uint16_t did,
                                              uint8_t* data, uint8_t length)
  {
  // Minimum payload: 2 bytes per cell
  if (length < FT5E_CELL_COUNT * 2) {
    ESP_LOGW(TAG, "Cell DID 0x%04X: payload too short (%u bytes, expected ≥%u)",
             did, length, FT5E_CELL_COUNT * 2);
    return;
  }

  BmsRestartCellVoltages();

  int decoded = 0;
  for (int i = 0; i < FT5E_CELL_COUNT; i++) {
    uint16_t mv = ((uint16_t)data[i * 2] << 8) | data[i * 2 + 1];
    mv *= FT5E_CELL_MV_SCALE;

    if (mv >= FT5E_CELL_MV_MIN && mv <= FT5E_CELL_MV_MAX) {
      BmsSetCellVoltage(i, (float)mv / 1000.0f);
      decoded++;
    } else {
      ESP_LOGW(TAG, "Cell %d: out-of-range value %u mV — skipped", i, mv);
    }
  }

  m_cell_count = decoded;
  MyMetrics.Find("xse.b.cell_count")->SetValue(decoded);
  MyMetrics.Find("xse.b.cell_did")->SetValue((int)did);

  ESP_LOGI(TAG, "Cell voltages updated: %d/%d cells decoded from DID 0x%04X",
           decoded, FT5E_CELL_COUNT, did);
  }


// ═══════════════════════════════════════════════════════════════════════════
// Shell commands
// ═══════════════════════════════════════════════════════════════════════════

// xse cells — print current cell voltages
void OvmsVehicleFiat500e::xse_cells(int verbosity, OvmsWriter* writer,
                                     OvmsCommand* cmd, int argc,
                                     const char* const* argv)
  {
  OvmsVehicleFiat500e* me = (OvmsVehicleFiat500e*) MyVehicleFactory.ActiveVehicle();
  if (!me) { writer->puts("No active vehicle"); return; }

  int cell_did = MyConfig.GetParamValueInt("xse", "bpcm.cell_did", 0);
  if (cell_did == 0) {
    writer->puts("Cell DID not configured.\n"
                 "Run 'xse scan auto' to discover it, then:\n"
                 "  config set xse bpcm.cell_did <DID>");
    return;
  }

  writer->printf("Cell DID: 0x%04X   Cells decoded last cycle: %d\n\n",
                 cell_did, me->m_cell_count);

  // Print cells in a 8-column table
  for (int i = 0; i < FT5E_CELL_COUNT; i++) {
    OvmsMetric* m = MyMetrics.Find(
      ("v.b.c.voltage." + std::to_string(i)).c_str());
    float v = m ? m->AsFloat() : 0.0f;

    if (i % 8 == 0) writer->printf("[%02d–%02d]  ", i, i+7);
    writer->printf("%5.3fV  ", v);
    if (i % 8 == 7) writer->printf("\n");
  }
  writer->printf("\n");
  }


// xse scan — probe BPCM DIDs to discover cell voltage DID
void OvmsVehicleFiat500e::xse_scan(int verbosity, OvmsWriter* writer,
                                    OvmsCommand* cmd, int argc,
                                    const char* const* argv)
  {
  OvmsVehicleFiat500e* me = (OvmsVehicleFiat500e*) MyVehicleFactory.ActiveVehicle();
  if (!me) { writer->puts("No active vehicle"); return; }

  const char* mode = argv[0];

  // ── xse scan stop ───────────────────────────────────────────────────────
  if (strcmp(mode, "stop") == 0) {
    if (me->m_scan_active) {
      me->m_scan_active = false;
      me->m_scan_writer = nullptr;
      writer->puts("Scan stopped.");
    } else {
      writer->puts("No scan in progress.");
    }
    return;
  }

  // ── xse scan auto ──────────────────────────────────────────────────────
  if (strcmp(mode, "auto") == 0) {
    writer->puts("Probing known Bosch BMS DIDs one by one (1 per second)...\n"
                 "Watch for responses with ≥192 bytes and values in 2500–4200 range.\n"
                 "Type 'xse scan stop' to abort.\n");

    // Build a small sequential scan across the candidate list
    // by flattening it into a contiguous range.
    // Simplest: just scan the first candidate; user can narrow down later.
    // We scan each candidate individually via the Ticker1 mechanism.
    // Here we pick the tightest useful range: 0x2001–0x2010, 0x4000–0x4030.
    // Practical: just scan 0x2000–0x4030 (0x2031 DIDs, ~33 minutes).
    // For a quick first pass, scan just the known candidates.

    // We queue candidates into a tight range via two back-to-back calls.
    // For simplicity, scan the two most-likely ranges:
    //   0x2000–0x2020   (pack status block)
    //   0x4000–0x4040   (cell data block)
    writer->puts("Pass 1: scanning 0x2000–0x2020 ...");
    me->m_scan_active  = true;
    me->m_scan_did     = 0x2000;
    me->m_scan_did_end = 0x2020;
    me->m_scan_writer  = writer;
    // Pass 2 will be queued when pass 1 completes (not yet implemented — user
    // can manually run 'xse scan 0x4000 0x4040' after pass 1 finishes).
    return;
  }

  // ── xse scan <start> <end> ──────────────────────────────────────────────
  if (argc < 2) {
    writer->puts("Usage: xse scan <start_hex> <end_hex>\n"
                 "       xse scan auto\n"
                 "       xse scan stop");
    return;
  }

  uint16_t start_did = (uint16_t) strtol(argv[0], nullptr, 16);
  uint16_t end_did   = (uint16_t) strtol(argv[1], nullptr, 16);

  if (end_did < start_did) {
    writer->puts("Error: end DID must be >= start DID");
    return;
  }
  if (end_did - start_did > 0x200) {
    writer->printf("Warning: scanning %u DIDs will take ~%u minutes.\n",
                   (uint32_t)(end_did - start_did + 1),
                   (uint32_t)(end_did - start_did + 1) / 60 + 1);
  }

  writer->printf("Scanning BPCM DIDs 0x%04X–0x%04X (1 per second)...\n"
                 "Type 'xse scan stop' to abort.\n", start_did, end_did);

  me->m_scan_active  = true;
  me->m_scan_did     = start_did;
  me->m_scan_did_end = end_did;
  me->m_scan_writer  = writer;
  }


// ═══════════════════════════════════════════════════════════════════════════
// CAN frame handlers (unchanged from original, with scan intercept added)
// ═══════════════════════════════════════════════════════════════════════════

void OvmsVehicleFiat500e::IncomingFrameCan1(CAN_frame_t* p_frame)
  {
  uint8_t *d = p_frame->data.u8;

  // ── Intercept raw BPCM UDS responses during DID scan ──────────────────
  // BPCM single-frame responses arrive here before the OVMS ISO-TP assembler
  // reassembles multi-frame ones.  For single-frame scan results (≤ 7 bytes
  // payload) the poll reply callback may NOT be called, so we catch them here.
  if (m_scan_active && m_scan_writer
      && p_frame->MsgID == FT5E_BPCM_RXID
      && p_frame->FIR.B.FF == CAN_frame_ext)
    {
    // d[0] = PCI byte: 0x0N = single frame (N bytes), 0x1N = first frame, etc.
    uint8_t pci = d[0] & 0xF0;
    uint8_t plen = d[0] & 0x0F;

    if (pci == 0x00 && plen >= 3 && d[1] == 0x62) {
      // Single-frame positive response: service 0x62 = 0x22+0x40
      uint16_t resp_did = ((uint16_t)d[2] << 8) | d[3];
      m_scan_writer->printf("  DID 0x%04X single-frame → %u payload bytes:"
                            " %02X %02X %02X\n",
                            resp_did, plen - 3, d[4], d[5], d[6]);
    } else if (pci == 0x10) {
      // First frame of a multi-frame response — OVMS assembler will deliver
      // the complete payload to IncomingPollReply().
      uint16_t total = (((uint16_t)(d[0] & 0x0F)) << 8) | d[1];
      m_scan_writer->printf("  → multi-frame response, %u total bytes"
                            " (see IncomingPollReply)\n", total);
    } else if (pci == 0x70 || (pci == 0x00 && d[1] == 0x7F)) {
      // Negative response (NRC)
      m_scan_writer->printf("  DID NRC: %02X %02X %02X\n", d[1], d[2], d[3]);
    }
    // Do NOT return here — fall through to existing frame handlers below
    // (this message ID won't match any of them, but keeps the flow clean).
    }

  switch (p_frame->MsgID) {

    case 0x10A006: // BRAKE_PEDAL (CAN-C passive)
      // d[0]/255 * 100 = % pressed; map to footbrake bool
      StandardMetrics.ms_v_env_footbrake->SetValue(d[0] > 0);
      break;

    case 0xC10A040: // MSG31B_EVCU
      {
      StandardMetrics.ms_v_bat_range_est->SetValue(d[0]);
      float soc = d[1] >> 1;
      StandardMetrics.ms_v_bat_soc->SetValue(soc);
      float pow = ((uint16_t) d[2] << 5) | (d[3] >> 3);
      StandardMetrics.ms_v_bat_energy_used->SetValue((pow / 100) - 24);
      break;
      }

    case 0x820A040: // MSG29_EVCU
      StandardMetrics.ms_v_charge_inprogress->SetValue(d[1] & 0x10);
      break;

    case 0x640A046: // MSG06_BPCM
      StandardMetrics.ms_v_charge_inprogress->SetValue(d[5] & 0x4);
      break;

    case 0x400A042: // EM_02
      StandardMetrics.ms_v_mot_temp->SetValue(((float)d[0]) - 50);
      StandardMetrics.ms_v_gen_temp->SetValue(((float)d[1]) - 50);
      StandardMetrics.ms_v_inv_temp->SetValue(((float)d[2]) - 50);
      break;

    case 0xC08A040: // MSG30_EVCU
      ft_v_acelec_pwr->SetValue(d[0] * 4);
      ft_v_htrelec_pwr->SetValue(d[4] * 4);
      break;

    case 0xC50A049: // MSG36_OBCM
      {
      unsigned int cvolt = ((unsigned int)d[1] << 8) | d[2];
      StandardMetrics.ms_v_charge_voltage->SetValue((float)cvolt / 10);
      unsigned int ccurr = ((unsigned int)d[3] << 8) | d[4];
      StandardMetrics.ms_v_charge_current->SetValue((float)ccurr / 5 - 50);
      unsigned int bvolt = ((unsigned int)d[5] << 8) | d[6];
      StandardMetrics.ms_v_bat_voltage->SetValue((float)bvolt / 10);
      StandardMetrics.ms_v_charge_temp->SetValue(d[0]);
      break;
      }

    case 0x840A046: // MSG08_BPCM
      {
      float btemp = (float)(((d[2] & 0x7F) << 1) | ((d[2] & 0x80) >> 7));
      StandardMetrics.ms_v_bat_temp->SetValue(btemp - 40);
      break;
      }

    default:
      break;
  }
}


void OvmsVehicleFiat500e::IncomingFrameCan2(CAN_frame_t* p_frame)
  {
  uint8_t *d = p_frame->data.u8;

  switch (p_frame->MsgID) {

    case 0x6214000: // STATUS_BCM
      StandardMetrics.ms_v_env_handbrake->SetValue(d[0] & 0x20);
      StandardMetrics.ms_v_door_fl->SetValue(d[1] & 0x4);
      StandardMetrics.ms_v_door_fr->SetValue(d[1] & 0x8);
      StandardMetrics.ms_v_door_trunk->SetValue(d[1] & 0x40);
      break;

    case 0x631400A: // STATUS_ECC2
      {
      unsigned int evapset = ((d[1] & 0x3F) << 2) + ((d[2] & 0xF8) >> 4);
      StandardMetrics.ms_v_env_cabinsetpoint->SetValue((float)evapset);
      switch (d[1] & 0xC0) {
        case 0x00: StandardMetrics.ms_v_env_valet->SetValue(false); break;
        case 0x40: StandardMetrics.ms_v_env_valet->SetValue(true);  break;
        case 0xC0: StandardMetrics.ms_v_env_valet->SetValue(true);  break;
        default:   StandardMetrics.ms_v_env_valet->SetValue(false); break;
      }
      break;
      }

    case 0xA194040: // STATUS_B_EVCU
      if      ((d[3] & 0x30) == 0x00) {
        StandardMetrics.ms_v_door_chargeport->SetValue(false);
        StandardMetrics.ms_v_charge_state->SetValue("topoff");
      } else if ((d[3] & 0x30) == 0x10) {
        StandardMetrics.ms_v_door_chargeport->SetValue(true);
        StandardMetrics.ms_v_charge_state->SetValue("charging");
      } else if ((d[3] & 0x30) == 0x20) {
        StandardMetrics.ms_v_door_chargeport->SetValue(true);
        StandardMetrics.ms_v_charge_state->SetValue("stopped");
      } else if ((d[3] & 0x30) == 0x30) {
        StandardMetrics.ms_v_door_chargeport->SetValue(false);
        StandardMetrics.ms_v_charge_state->SetValue("done");
      }
      break;

    case 0x6414000: // STATUS_BCM4
      StandardMetrics.ms_v_env_locked->SetValue(d[3] & 0x40);
      break;

    case 0x63D4000: // ENVIRONMENTAL_CONDITIONS
      if (d[0] != 0)
        StandardMetrics.ms_v_env_temp->SetValue((d[0] * 0.5f) - 40.0f);
      else
        StandardMetrics.ms_v_bat_voltage->SetValue((d[1] & 0x7F) * 0.16f);
      break;

    case 0xC414000: // HUMIDITY_000
      {
      float itemp = (float)(((uint16_t)d[3] << 1) | ((d[4] & 0x80) >> 7));
      StandardMetrics.ms_v_env_cabintemp->SetValue(itemp * 0.5f - 40.0f);
      break;
      }

    case 0xC014003: // TRIP_A_B
      {
      float vodo = (float)(((d[1] & 0x0F) << 16) | (d[2] << 8) | d[3]);
      StandardMetrics.ms_v_pos_odometer->SetValue(vodo);
      break;
      }

    default:
      break;
  }
}


// ═══════════════════════════════════════════════════════════════════════════
// Vehicle commands (unchanged from original)
// ═══════════════════════════════════════════════════════════════════════════

OvmsVehicle::vehicle_command_t OvmsVehicleFiat500e::CommandWakeup()
  {
  CAN_frame_t frame = {};
  frame.FIR.B.FF  = CAN_frame_ext;
  frame.MsgID     = 0xE094000;
  frame.FIR.B.DLC = 6;
  frame.data.u8[1] = 0x01;
  for (int i = 0; i < 3; i++) { m_can2->Write(&frame); vTaskDelay(50 / portTICK_PERIOD_MS); }
  return Success;
  }

OvmsVehicle::vehicle_command_t OvmsVehicleFiat500e::CommandStartCharge()
  {
  CAN_frame_t frame = {};
  frame.FIR.B.FF  = CAN_frame_ext;
  frame.MsgID     = 0xC41401F;
  frame.FIR.B.DLC = 1;
  frame.data.u8[0] = 0x20;
  for (int i = 0; i < 3; i++) { m_can2->Write(&frame); vTaskDelay(50 / portTICK_PERIOD_MS); }
  return Success;
  }

OvmsVehicle::vehicle_command_t OvmsVehicleFiat500e::CommandStopCharge()
  {
  CAN_frame_t frame = {};
  frame.FIR.B.FF  = CAN_frame_ext;
  frame.MsgID     = 0xC41401F;
  frame.FIR.B.DLC = 1;
  frame.data.u8[0] = 0x40;
  for (int i = 0; i < 3; i++) { m_can2->Write(&frame); vTaskDelay(50 / portTICK_PERIOD_MS); }
  return Success;
  }

OvmsVehicle::vehicle_command_t OvmsVehicleFiat500e::CommandLock(const char* pin)
  {
  CAN_frame_t frame = {};
  frame.FIR.B.FF  = CAN_frame_ext;
  frame.MsgID     = 0xC41401F;
  frame.FIR.B.DLC = 1;
  frame.data.u8[0] = 0x08;
  for (int i = 0; i < 3; i++) { m_can2->Write(&frame); vTaskDelay(50 / portTICK_PERIOD_MS); }
  return Success;
  }

OvmsVehicle::vehicle_command_t OvmsVehicleFiat500e::CommandUnlock(const char* pin)
  {
  CAN_frame_t frame = {};
  frame.FIR.B.FF  = CAN_frame_ext;
  frame.MsgID     = 0xC41401F;
  frame.FIR.B.DLC = 1;
  frame.data.u8[0] = 0x10;
  for (int i = 0; i < 3; i++) { m_can2->Write(&frame); vTaskDelay(50 / portTICK_PERIOD_MS); }
  return Success;
  }

OvmsVehicle::vehicle_command_t OvmsVehicleFiat500e::CommandActivateValet(const char* pin)
  {
  CAN_frame_t frame_wu = {};
  frame_wu.FIR.B.FF  = CAN_frame_ext;
  frame_wu.MsgID     = 0xE094000;
  frame_wu.FIR.B.DLC = 6;
  frame_wu.data.u8[1] = 0x01;

  CAN_frame_t frame = {};
  frame.FIR.B.FF  = CAN_frame_ext;
  frame.MsgID     = 0xE194031;
  frame.FIR.B.DLC = 2;
  frame.data.u8[0] = 0x20;
  frame.data.u8[1] = 0x64;

  m_can2->Write(&frame_wu);
  vTaskDelay(500 / portTICK_PERIOD_MS);
  m_can2->Write(&frame);
  return Success;
  }

OvmsVehicle::vehicle_command_t OvmsVehicleFiat500e::CommandDeactivateValet(const char* pin)
  {
  CAN_frame_t frame = {};
  frame.FIR.B.FF  = CAN_frame_ext;
  frame.MsgID     = 0xE194031;
  frame.FIR.B.DLC = 2;
  frame.data.u8[0] = 0x40;
  frame.data.u8[1] = 0x64;
  m_can2->Write(&frame);
  vTaskDelay(50 / portTICK_PERIOD_MS);
  m_can2->Write(&frame);
  StandardMetrics.ms_v_env_valet->SetValue(false);
  return Success;
  }

OvmsVehicle::vehicle_command_t OvmsVehicleFiat500e::CommandHomelink(int button, int durationms)
  {
  if (button == 0) {    // Horn + lights ON
    CAN_frame_t frame = {};
    frame.FIR.B.FF  = CAN_frame_ext;
    frame.MsgID     = 0xC41401F;
    frame.FIR.B.DLC = 1;
    frame.data.u8[0] = 0x02;
    for (int i = 0; i < 3; i++) { m_can2->Write(&frame); vTaskDelay(50 / portTICK_PERIOD_MS); }
    return Success;
  }
  if (button == 1) {    // Horn + lights OFF
    CAN_frame_t frame = {};
    frame.FIR.B.FF  = CAN_frame_ext;
    frame.MsgID     = 0xC41401F;
    frame.FIR.B.DLC = 1;
    frame.data.u8[0] = 0x00;
    for (int i = 0; i < 3; i++) { m_can2->Write(&frame); vTaskDelay(50 / portTICK_PERIOD_MS); }
    return Success;
  }
  if (button == 2) {    // Manual BPCM DID 0x2001 request (debug)
    SendBpcmRequest(0x2001);
    return Success;
  }
  return NotImplemented;
  }


// ── Vehicle registration ───────────────────────────────────────────────────

class OvmsVehicleFiat500eInit
  {
  public: OvmsVehicleFiat500eInit();
  }
  OvmsVehicleFiat500eInit __attribute__ ((init_priority (9000)));

OvmsVehicleFiat500eInit::OvmsVehicleFiat500eInit()
  {
  ESP_LOGI(TAG, "Registering Vehicle: FIAT 500e (9000)");
  MyVehicleFactory.RegisterVehicle<OvmsVehicleFiat500e>("FT5E", "Fiat 500e");
  }
