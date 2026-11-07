
import os

import fal_client
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Load the private API key from backend/.env
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=True)
app = FastAPI(title="VisionAI Video Generator")

# Local development only. We will restrict this before public deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "message": "Welcome to VisionAI!",
        "status": "Backend is running"
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/generate")
def generate_video(data: dict):
    prompt = str(data.get("prompt", "")).strip()
    style = str(data.get("style", "cinematic")).lower()
    requested_duration = data.get("duration", 5)

    if not prompt:
        raise HTTPException(
            status_code=400,
            detail="Please enter a video description."
        )

    if len(prompt) > 20000:
        raise HTTPException(
            status_code=400,
            detail="Your prompt is too long."
        )

    if not os.getenv("FAL_KEY"):
        raise HTTPException(
            status_code=500,
            detail="API key is missing. Check your backend .env file."
        )

    # Map the current website's 5/10-second choices
    # to durations supported by the video model.
    duration_map = {
        5: "6s",
        10: "8s",
        6: "6s",
        8: "8s"
    }

    try:
        duration = duration_map.get(
            int(requested_duration), "6s"
        )
    except (TypeError, ValueError):
        duration = "6s"

    style_descriptions = {
        "cinematic": "cinematic film style",
        "realistic": "photorealistic visual style",
        "anime": "anime animation style",
        "3d": "high-quality 3D animation style"
    }

    final_prompt = (
        prompt + ". Visual style: "
        + style_descriptions.get(style, "cinematic film style")
    )

    try:
        result = fal_client.run(
            "fal-ai/veo3.1/fast",
            arguments={
                "prompt": final_prompt,
                "duration": duration,
                "aspect_ratio": "16:9",
                "resolution": "720p",
                "generate_audio": False
            },
            timeout=600
        )

        video_url = result.get("video", {}).get("url")

        if not video_url:
            raise HTTPException(
                status_code=502,
                detail="The AI service did not return a video."
            )

        return {
            "message": "Video generated successfully!",
            "status": "completed",
            "video_url": video_url,
            "duration": duration,
            "style": style
        }

    except HTTPException:
        raise

    except Exception as exc:
        print(
            f"fal.ai error ({type(exc).__name__}): {exc}",
            flush=True
        )
        raise HTTPException(
            status_code=502,
            detail="Video generation failed. Check the backend terminal."
        )