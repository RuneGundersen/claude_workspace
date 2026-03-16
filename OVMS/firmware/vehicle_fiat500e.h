/*
;    Project:       Open Vehicle Monitor System
;    Date:          5th July 2018
;    Modified:      2026 — UDS polling expanded (VCM + BMS + charger)
;
;    Changes:
;    1.0  Initial release
;    1.1  Add BPCM UDS polling and per-cell voltage metrics
;    1.2  Add VCM driving data, BMS battery data, charger data polling
;
;    (C) 2021       Guenther Huck
;    (C) 2011       Michael Stegen / Stegen Electronics
;    (C) 2011-2018  Mark Webb-Johnson
;    (C) 2011        Sonny Chen @ EPRO/DX
;
; MIT License (see full text in .cpp)
*/

#ifndef __VEHICLE_FIAT500E_H__
#define __VEHICLE_FIAT500E_H__

#include "vehicle.h"
#include "vehicle_poller.h"

using namespace std;

// ── UDS addresses (CAN1, 500 kbps, 29-bit extended IDs) ──────────────────
// Format: 0x18DA<ECU><TSTR> for request, 0x18DA<TSTR><ECU> for response

// ECU 0x42 — VCM (Vehicle Control Module / inverter / motor controller)
// Also used for cell-voltage BPCM scan (legacy naming kept)
#define FT5E_VCM_TXID   0x18DA42F1
#define FT5E_VCM_RXID   0x18DAF142
#define FT5E_BPCM_TXID  FT5E_VCM_TXID   // back-compat alias
#define FT5E_BPCM_RXID  FT5E_VCM_RXID

// ECU 0x44 — BMS (Battery Management System)
#define FT5E_BMS_TXID   0x18DA44F1
#define FT5E_BMS_RXID   0x18DAF144

// ECU 0x47 — OBC (On-Board Charger)
#define FT5E_OBC_TXID   0x18DA47F1
#define FT5E_OBC_RXID   0x18DAF147

// ECU 0xA1 — TPMS (Tire Pressure Monitoring System), CAN2/B-CAN 50 kbps
#define FT5E_TPMS_TXID    0x18DAA1F1
#define FT5E_TPMS_RXID    0x18DAF1A1
#define FT5E_TPMS_DID_FL  0x40A1   // front-left  tire pressure
#define FT5E_TPMS_DID_FR  0x40A2   // front-right tire pressure
#define FT5E_TPMS_DID_RL  0x40A3   // rear-left   tire pressure
#define FT5E_TPMS_DID_RR  0x40A4   // rear-right  tire pressure

// ── Battery pack geometry ──────────────────────────────────────────────────
#define FT5E_CELL_COUNT 96

// ── Poll table capacity ────────────────────────────────────────────────────
#define FT5E_POLL_MAX   32

// ── Known candidate DIDs for per-cell voltages (Bosch BMS) ────────────────
static const uint16_t FT5E_CELL_DID_CANDIDATES[] = {
  0x4020, 0x4000, 0x4030, 0x2001, 0x2010, 0x2100, 0xD001, 0x0000
};


class OvmsVehicleFiat500e : public OvmsVehicle
  {
  public:
    OvmsVehicleFiat500e();
    ~OvmsVehicleFiat500e();

  public:
    void IncomingFrameCan1(CAN_frame_t* p_frame) override;
    void IncomingFrameCan2(CAN_frame_t* p_frame) override;
    void IncomingPollReply(const OvmsPoller::poll_job_t &job,
                           uint8_t* data, uint8_t length) override;

    vehicle_command_t CommandWakeup() override;
    vehicle_command_t CommandStartCharge() override;
    vehicle_command_t CommandStopCharge() override;
    vehicle_command_t CommandLock(const char* pin) override;
    vehicle_command_t CommandUnlock(const char* pin) override;
    vehicle_command_t CommandActivateValet(const char* pin) override;
    vehicle_command_t CommandDeactivateValet(const char* pin) override;
    vehicle_command_t CommandHomelink(int button, int durationms) override;

    static void xse_cells(int verbosity, OvmsWriter* writer,
                          OvmsCommand* cmd, int argc, const char* const* argv);
    static void xse_scan(int verbosity, OvmsWriter* writer,
                         OvmsCommand* cmd, int argc, const char* const* argv);

  protected:
    void Ticker1(uint32_t ticker) override;

    // ── Existing metrics ───────────────────────────────────────────────────
    OvmsMetricFloat *mt_mb_trip_reset;
    OvmsMetricFloat *mt_mb_trip_start;
    OvmsMetricFloat *mt_mb_consumption_start;
    OvmsMetricFloat *mt_mb_eco_accel;
    OvmsMetricFloat *mt_mb_eco_const;
    OvmsMetricFloat *mt_mb_eco_coast;
    OvmsMetricFloat *mt_mb_eco_score;
    OvmsMetricFloat *mt_mb_fl_speed;
    OvmsMetricFloat *mt_mb_fr_speed;
    OvmsMetricFloat *mt_mb_rl_speed;
    OvmsMetricFloat *mt_mb_rr_speed;
    OvmsMetricFloat *ft_v_acelec_pwr;
    OvmsMetricFloat *ft_v_htrelec_pwr;

    // ── VCM UDS metrics (new) ──────────────────────────────────────────────
    OvmsMetricFloat *xse_v_m_torque;        // motor torque (Nm)
    OvmsMetricFloat *xse_v_m_torque_tgt;    // torque target (Nm)
    OvmsMetricFloat *xse_v_m_coolant_temp;  // motor coolant temp (°C)

    // ── Cell voltage polling ───────────────────────────────────────────────
    uint16_t m_cell_did;
    int      m_cell_count;

    // ── DID scan state ─────────────────────────────────────────────────────
    bool       m_scan_active;
    uint16_t   m_scan_did;
    uint16_t   m_scan_did_end;
    OvmsWriter *m_scan_writer;

    // ── Internal helpers ───────────────────────────────────────────────────
    void SendBpcmRequest(uint16_t did);
    void DecodeCellVoltages(uint16_t did, uint8_t* data, uint8_t length);
    void UpdatePollState();
    void BuildPollTable();
  };

#endif // __VEHICLE_FIAT500E_H__
