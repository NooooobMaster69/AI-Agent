# V2 Testing Guide

## 1) Setup

```bash
python -m pip install -r requirements.txt
playwright install chromium
```

## 2) Environment check

```bash
python -m app_v2.main_v2 check-env
```

If all dependencies are listed as `OK`, the environment is ready for runtime testing.

## 3) Run flow

### Start a run

```bash
python -m app_v2.main_v2 run "your task here"
```

### Inspect run

```bash
python -m app_v2.main_v2 show <run_id>
```

### Generate resume decision (for paused runs)

```bash
python -m app_v2.main_v2 decide <run_id>
```

### Resume run

```bash
python -m app_v2.main_v2 resume <run_id>
```

## 4) Artifacts to verify

- `runs/run_<id>.json`
- `artifacts/final_report_v2_<id>.md`
- `artifacts/pause_packet_v2_<id>.json` (when paused)
- `artifacts/resume_decision_v2_<id>.json` (after `decide`)
- `artifacts/final_report_v2_resume_<id>.md` (after resume)
