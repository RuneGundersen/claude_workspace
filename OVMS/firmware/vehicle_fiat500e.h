/*
;    Project:       Open Vehicle Monitor System
;    Date:          5th July 2018
;    Modified:      2026 — cell voltage polling added
;
;    Changes:
;    1.0  Initial release
;    1.1  Add UDS/ISO-TP BPCM polling and per-cell voltage metrics
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

using namespace std;

// ── BPCM UDS addresses (CAN1, 500 kbps, 29-bit extended IDs) ──────────────
// Physical addressing: tester=0xF1, BPCM ECU=0x42
// Format: 0x18DA<ECU><TSTR> for request, 0x18DA<TSTR><ECU> for response
#define FT5E_BPCM_TXID  0x18DA42F1   // tester → BPCM
#define FT5E_BPCM_RXID  0x18DAF142   // BPCM  → tester

// ── Battery pack geometry ──────────────────────────────────────────────────
// 2013-2019 Fiat 500e: 24 kWh, 96 series cells (~3.3 V each, 374 V nominal)
#define FT5E_CELL_COUNT 96

// ── Known candidate DIDs for per-cell voltages (Bosch BMS) ────────────────
// These are tried in order by the "xse scan auto" command.
// Update xse.bpcm.cell_did once you find the right one.
static const uint16_t FT5E_CELL_DID_CANDIDATES[] = {
  0x4020,   // Common Bosch BMS cell voltage array
  0x4000,   // Cell block 0
  0x4030,   // Cell group data
  0x2001,   // Pack general status (may embed cell block sub-records)
  0x2010,   // Pack extended status
  0x2100,   // BMS diagnostics
  0xD001,   // Extended manufacturer data
  0x0000    // sentinel
};


class OvmsVehicleFiat500e : public OvmsVehicle
  {
  public:
    OvmsVehicleFiat500e();
    ~OvmsVehicleFiat500e();

  public:
    void IncomingFrameCan1(CAN_frame_t* p_frame) override;
    void IncomingFrameCan2(CAN_frame_t* p_frame) override;

    // UDS poll reply handler
    void IncomingPollReply(canbus* bus, uint16_t type, uint16_t pid,
                           uint8_t* data, uint8_t length,
                           uint16_t mlremain) override;

    vehicle_command_t CommandWakeup() override;
    vehicle_command_t CommandStartCharge() override;
    vehicle_command_t CommandStopCharge() override;
    vehicle_command_t CommandLock(const char* pin) override;
    vehicle_command_t CommandUnlock(const char* pin) override;
    vehicle_command_t CommandActivateValet(const char* pin) override;
    vehicle_command_t CommandDeactivateValet(const char* pin) override;
    vehicle_command_t CommandHomelink(int button, int durationms) override;

    // Shell commands
    static void xse_cells(int verbosity, OvmsWriter* writer,
                          OvmsCommand* cmd, int argc,
                          const char* const* argv);
    static void xse_scan(int verbosity, OvmsWriter* writer,
                         OvmsCommand* cmd, int argc,
                         const char* const* argv);

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

    // ── Cell voltage polling ───────────────────────────────────────────────
    uint16_t m_cell_did;       // active DID for cell voltages (0 = disabled)
    int      m_cell_count;     // cells decoded in last reply (for validation)

    // ── DID scan state ─────────────────────────────────────────────────────
    // "xse scan <start> <end>" sends UDS 0x22 requests one per second
    // and logs each BPCM response; used to discover cell-voltage DID.
    bool       m_scan_active;
    uint16_t   m_scan_did;         // current scan DID
    uint16_t   m_scan_did_end;     // last DID to scan (inclusive)
    OvmsWriter *m_scan_writer;     // console to write results to

    // ── Internal helpers ───────────────────────────────────────────────────
    void SendBpcmRequest(uint16_t did);    // raw UDS 0x22 on CAN1
    void DecodeCellVoltages(uint16_t did, uint8_t* data, uint8_t length);
    void UpdatePollState();
  };

#endif // __VEHICLE_FIAT500E_H__
