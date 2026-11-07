
import os
import uuid
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "generated"
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="VisionAI Free Video Creator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/videos", StaticFiles(directory=str(OUTPUT_DIR)), name="videos")

WIDTH = 1280
HEIGHT = 720
FPS = 24


@app.get("/")
def home():
    return {
        "message": "Welcome to VisionAI!",
        "status": "Free video creator is running"
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


def get_font(size):
    windows_font = Path("C:/Windows/Fonts/arial.ttf")
    try:
        return ImageFont.truetype(str(windows_font), size)
    except OSError:
        return ImageFont.load_default()


def make_scene(image_path, caption, output_path):
    image = Image.open(image_path).convert("RGB")
    image.thumbnail((WIDTH, HEIGHT))

    background = Image.new("RGB", (WIDTH, HEIGHT), "black")
    x = (WIDTH - image.width) // 2
    y = (HEIGHT - image.height) // 2
    background.paste(image, (x, y))

    if caption:
        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        font = get_font(38)
        text = caption[:100]

        box = draw.textbbox((0, 0), text, font=font)
        text_width = box[2] - box[0]
        text_height = box[3] - box[1]

        tx = (WIDTH - text_width) // 2
        ty = HEIGHT - text_height - 65

        draw.rounded_rectangle(
            (tx - 25, ty - 15, tx + text_width + 25,
             ty + text_height + 15),
            radius=15,
            fill=(0, 0, 0, 170)
        )

        draw.text((tx, ty), text, font=font, fill="white")
        background = Image.alpha_composite(
            background.convert("RGBA"), overlay
        ).convert("RGB")

    background.save(output_path, quality=92)


@app.post("/create-free-video")
async def create_free_video(
    images: list[UploadFile] = File(...),
    captions: str = Form(""),
    seconds_per_image: int = Form(3)
):
    if not images:
        raise HTTPException(400, "Upload at least one image.")

    if len(images) > 20:
        raise HTTPException(400, "Maximum 20 images allowed.")

    if seconds_per_image < 1 or seconds_per_image > 10:
        raise HTTPException(400, "Duration must be 1 to 10 seconds.")

    captions_list = captions.split("|") if captions else []
    job_id = uuid.uuid4().hex

    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True)

    scene_files = []
    input_files = []

    try:
        for index, upload in enumerate(images):
            content = await upload.read()

            if len(content) > 10 * 1024 * 1024:
                raise HTTPException(400, "Each image must be under 10 MB.")

            if not content:
                raise HTTPException(400, "An uploaded image is empty.")

            input_path = job_dir / f"input_{index}.img"
            scene_path = job_dir / f"scene_{index:03d}.png"

            input_path.write_bytes(content)
            input_files.append(input_path)

            caption = (
                captions_list[index].strip()
                if index < len(captions_list)
                else ""
            )

            make_scene(input_path, caption, scene_path)
            scene_files.append(scene_path)

        output_path = job_dir / "visionai_video.mp4"
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

        command = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel", "error"
        ]

        for scene in scene_files:
            command.extend(["-loop", "1", "-t", str(seconds_per_image),
                            "-i", str(scene)])

        filter_parts = []

        for index in range(len(scene_files)):
            filter_parts.append(
                f"[{index}:v]fps={FPS},"
                f"scale={WIDTH}:{HEIGHT},"
                f"setsar=1,format=yuv420p[v{index}]"
            )

        concat_inputs = "".join(
            f"[v{index}]" for index in range(len(scene_files))
        )

        filter_parts.append(
            f"{concat_inputs}concat=n={len(scene_files)}:v=1:a=0[outv]"
        )

        command.extend([
            "-filter_complex", ";".join(filter_parts),
            "-map", "[outv]",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path)
        ])

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr[-1500:])

        return {
            "status": "completed",
            "message": "Your free video is ready!",
            "video_url": f"http://127.0.0.1:8000/videos/{job_id}/visionai_video.mp4",
            "duration": len(scene_files) * seconds_per_image,
            "scenes": len(scene_files)
        }

    except HTTPException:
        raise

    except Exception as error:
        print("Video creation error:", error, flush=True)
        raise HTTPException(
            500,
            "Video creation failed. Check the backend terminal."
        )

    finally:
        for upload in images:
            await upload.close()
