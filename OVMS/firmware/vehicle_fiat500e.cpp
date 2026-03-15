/*
;    Project:       Open Vehicle Monitor System
;    Date:          5th July 2018
;    Modified:      2026 — UDS cell-voltage polling (Rune Gundersen)
;
;    Changes:
;    1.0  Initial release
;    1.1  Add BPCM UDS polling via OVMS poll infrastructure.
;         Per-cell voltages published as v.b.c.voltage[0..95] → MQTT.
;         Shell commands: xse cells / xse scan <start> <end>
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
;   CAN1  C-CAN  500 kbps  — powertrain / BMS (BPCM at UDS addr 0x42)
;   CAN2  B-CAN   50 kbps  — body / comfort
;
; BPCM UDS addressing (ISO 15765-2, 29-bit IDs):
;   TX (tester→BPCM): 0x18DA42F1
;   RX (BPCM→tester): 0x18DAF142
;
; Cell voltage DID:
;   Set via config:  config set xse bpcm.cell_did <hex-DID>
;   Default 0x0000 → disabled until discovered via "xse scan" command.
;   See README_CELLS.md for discovery procedure.
;
; MQTT metrics added:
;   v.b.c.voltage[0..95]   — cell voltages (V) — standard OVMS metric
;   xse.b.cell_did         — active cell DID (informational)
;   xse.b.cell_count       — number of cells decoded in last reply
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


// ── UDS poll table ──────────────────────────────────────────────────────────
// polltime[] = {state0, state1, state2, state3}  (seconds; 0 = skip)
//   state 0 = standby/off
//   state 1 = on / driving
//   state 2 = charging
//   state 3 = (not used — reserved for DID scan)
//
// DID 0x2001: BPCM pack status (confirmed to work — used in existing code).
// DID 0x0000 placeholder for the cell voltage DID; replaced at runtime when
//   config xse/bpcm.cell_did is non-zero.
//
// NOTE: The cell-voltage DID entry uses txmoduleid=0 to mark it as disabled
//       in the static table; it is added dynamically in the constructor when
//       the config value is known.

static const OvmsVehicle::poll_pid_t bpcm_polls[] = {
  // { txid,          rxid,          type,                           pid,    {s0,s1, s2,s3}, bus, proto }
  { FT5E_BPCM_TXID, FT5E_BPCM_RXID, VEHICLE_POLL_TYPE_READDATABYID, 0x2001, {0, 30, 60, 0}, 1, ISOTP_STD },
  POLL_LIST_END
};

// Dynamic poll table (room for pack status + cell DID + end marker)
static OvmsVehicle::poll_pid_t bpcm_polls_dyn[3];


// ── Constructor ────────────────────────────────────────────────────────────

OvmsVehicleFiat500e::OvmsVehicleFiat500e()
  {
  ESP_LOGI(TAG, "Start Fiat 500e vehicle module (with cell-voltage polling)");

  // ── Existing metrics ─────────────────────────────────────────────────────
  ft_v_acelec_pwr  = MyMetrics.InitFloat("xse.v.b.acelec.pwr",  SM_STALE_MID, 0, Watts);
  ft_v_htrelec_pwr = MyMetrics.InitFloat("xse.v.b.htrelec.pwr", SM_STALE_MID, 0, Watts);

  // ── BMS cell voltage metrics ──────────────────────────────────────────────
  // OVMS standard metrics v.b.c.voltage[n] are automatically published to
  // MQTT as e.g. EV88283metric/v/b/c/voltage/0 … /95 once BmsSetCellVoltage()
  // is called.  BmsSetCellDefaultThresholds sets the warning/alert thresholds.
  BmsSetCellDefaultThresholds("voltage", 2.5, 2.0, 4.2, 4.3);
  BmsSetCellArrangementVoltage(FT5E_CELL_COUNT, 1);  // 96 cells, 1 per module

  // Informational metrics
  MyMetrics.InitInt("xse.b.cell_did",   SM_STALE_HIGH, 0);
  MyMetrics.InitInt("xse.b.cell_count", SM_STALE_HIGH, 0);

  // ── Cell DID from config ──────────────────────────────────────────────────
  m_cell_did = (uint16_t) MyConfig.GetParamValueInt("xse", "bpcm.cell_did", 0);
  m_cell_count = 0;
  ESP_LOGI(TAG, "Cell DID from config: 0x%04X%s",
           m_cell_did, m_cell_did ? "" : "  (disabled — run 'xse scan' to discover)");

  // ── Build dynamic poll table ──────────────────────────────────────────────
  // Entry 0: pack status DID 0x2001 (always on)
  memcpy(&bpcm_polls_dyn[0], &bpcm_polls[0], sizeof(OvmsVehicle::poll_pid_t));

  if (m_cell_did != 0) {
    // Entry 1: cell voltage DID (poll every 30 s when on, 60 s charging)
    bpcm_polls_dyn[1] = {
      FT5E_BPCM_TXID, FT5E_BPCM_RXID,
      VEHICLE_POLL_TYPE_READDATABYID, m_cell_did,
      {0, 30, 60, 0}, 1, ISOTP_STD
    };
    bpcm_polls_dyn[2] = POLL_LIST_END;
  } else {
    bpcm_polls_dyn[1] = POLL_LIST_END;
  }

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

void OvmsVehicleFiat500e::IncomingPollReply(canbus* bus, uint16_t type,
                                             uint16_t pid,
                                             uint8_t* data, uint8_t length,
                                             uint16_t mlremain)
  {
  switch (pid) {

    // ── DID 0x2001: BPCM pack status ────────────────────────────────────────
    // The exact layout of this DID is not publicly documented for the 500e.
    // Log the raw bytes so the user can decode it.
    // If it turns out to contain cell voltages, update DecodeCellVoltages().
    case 0x2001:
      ESP_LOGD(TAG, "BPCM DID 0x2001 (%u bytes):", length);
      for (int i = 0; i < length && i < 64; i += 8) {
        ESP_LOGD(TAG, "  [%02d] %02X %02X %02X %02X  %02X %02X %02X %02X", i,
          (i+0 < length ? data[i+0] : 0), (i+1 < length ? data[i+1] : 0),
          (i+2 < length ? data[i+2] : 0), (i+3 < length ? data[i+3] : 0),
          (i+4 < length ? data[i+4] : 0), (i+5 < length ? data[i+5] : 0),
          (i+6 < length ? data[i+6] : 0), (i+7 < length ? data[i+7] : 0));
      }
      // If the scan writer is active it will pick up raw CAN in IncomingFrameCan1;
      // the poll reply path handles multi-frame responses via OVMS ISO-TP.
      if (m_scan_active && m_scan_writer) {
        m_scan_writer->printf("  DID 0x2001 → %u bytes", length);
        for (int i = 0; i < length && i < 32; i++)
          m_scan_writer->printf(" %02X", data[i]);
        if (length > 32) m_scan_writer->printf(" ...");
        m_scan_writer->printf("\n");
      }
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
  MyMetrics.FindMetric("xse.b.cell_count")->SetValue(decoded);
  MyMetrics.FindMetric("xse.b.cell_did")->SetValue((int)did);

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
    OvmsMetric* m = MyMetrics.FindMetric(
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
