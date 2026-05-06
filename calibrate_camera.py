from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    base = Path(__file__).resolve().parent
    cfg_path = base / "config.json"
    cfg = _load_json(cfg_path)
    cam = cfg.setdefault("camera", {})
    deskew = cam.setdefault("deskew", {})
    raw_path = base / str(cam.get("output_dir", "camera_captures")) / "latest_raw.jpg"
    if not raw_path.exists():
        print("Take a snapshot first, then run calibration.")
        return 1
    img = cv2.imread(str(raw_path))
    if img is None:
        print("Failed to read latest_raw.jpg")
        return 1

    points: list[list[int]] = []
    display = img.copy()
    out_size = deskew.get("output_size", [1200, 1200])
    out_w, out_h = int(out_size[0]), int(out_size[1])

    labels = ["TL", "TR", "BR", "BL"]

    def redraw() -> None:
        nonlocal display
        display = img.copy()
        for i, p in enumerate(points):
            cv2.circle(display, tuple(p), 5, (0, 255, 0), -1)
            cv2.putText(display, labels[i], (p[0] + 8, p[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    def on_click(event, x, y, _flags, _param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
            points.append([int(x), int(y)])
            redraw()

    cv2.namedWindow("Ray5 Calibration", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("Ray5 Calibration", on_click)
    redraw()

    while True:
        view = display.copy()
        next_label = labels[len(points)] if len(points) < 4 else "DONE"
        cv2.putText(
            view,
            f"Click order TL,TR,BR,BL. Next: {next_label}. S save, R reset, Q quit.",
            (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            2,
        )
        if len(points) == 4:
            src = np.array(points, dtype=np.float32)
            dst = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], dtype=np.float32)
            mat = cv2.getPerspectiveTransform(src, dst)
            preview = cv2.warpPerspective(img, mat, (out_w, out_h))
            cv2.imshow("Deskew Preview", preview)
        cv2.imshow("Ray5 Calibration", view)
        key = cv2.waitKey(30) & 0xFF
        if key in (ord("q"), 27):
            break
        if key == ord("r"):
            points.clear()
            redraw()
            cv2.destroyWindow("Deskew Preview")
        if key == ord("s") and len(points) == 4:
            deskew["enabled"] = True
            deskew["source_points"] = points
            deskew["output_size"] = [out_w, out_h]
            _save_json(cfg_path, cfg)
            print("Saved deskew points to config.json")
            break

    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
