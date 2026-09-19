import json
import subprocess
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="MI50 Monitor")

HISTORY_LEN = 60
history: dict[str, dict[str, deque]] = defaultdict(
    lambda: defaultdict(lambda: deque(maxlen=HISTORY_LEN))
)
last_data: list[dict] = []

HERE = Path(__file__).parent
HTML_CONTENT = (HERE / "templates" / "index.html").read_text()


def fetch_gpu_data() -> list[dict]:
    cmd = [
        "rocm-smi", "--json",
        "--showtemp", "--showmeminfo", "vram",
        "--showuse", "--showproductname", "--showid", "--showfan",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        raw = json.loads(result.stdout)
    except Exception:
        return last_data

    now = datetime.now().isoformat()
    cards = []
    for key in sorted(raw.keys(), key=lambda k: int(k.replace("card", ""))):
        info = raw[key]
        cards.append({
            "id": key,
            "name": info.get("Card series", "Unknown"),
            "model": info.get("Card model", ""),
            "sku": info.get("Card SKU", ""),
            "temp_edge": _float(info.get("Temperature (Sensor edge) (C)")),
            "temp_junction": _float(info.get("Temperature (Sensor junction) (C)")),
            "temp_memory": _float(info.get("Temperature (Sensor memory) (C)")),
            "fan_speed": _float(info.get("Fan speed (%)")),
            "fan_rpm": _int(info.get("Fan RPM")),
            "gpu_use": _float(info.get("GPU use (%)")),
            "vram_total": _int(info.get("VRAM Total Memory (B)")),
            "vram_used": _int(info.get("VRAM Total Used Memory (B)")),
            "timestamp": now,
        })

        gid = key
        for temp_key in ("temp_edge", "temp_junction", "temp_memory"):
            val = cards[-1][temp_key]
            if val is not None:
                history[gid][temp_key].append({"t": now, "v": val})
        use_val = cards[-1]["gpu_use"]
        if use_val is not None:
            history[gid]["gpu_use"].append({"t": now, "v": use_val})

    if cards:
        last_data.clear()
        last_data.extend(cards)
    return cards


def _float(v):
    if v is None or v == "N/A":
        return None
    try:
        return round(float(v), 1)
    except (ValueError, TypeError):
        return None


def _int(v):
    if v is None or v == "N/A":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


@app.on_event("startup")
async def startup():
    fetch_gpu_data()


@app.get("/api/gpus")
async def api_gpus():
    cards = fetch_gpu_data()
    result = []
    for c in cards:
        gid = c["id"]
        result.append({
            **c,
            "history": {
                k: list(v)
                for k, v in history[gid].items()
            },
        })
    return result


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_CONTENT
