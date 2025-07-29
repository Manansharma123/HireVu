# Interview Bot – Intelligent AI Interview Platform

A privacy-aware, web-based AI Interview Bot using FastAPI. It features LLM-powered resume analysis, real-time proctoring, auto-generated interview questions, conversational audio UX, and PDF reporting.

**Developed by:** Manan Sharma – AI Developer

---

## Features

- **📄 PDF Resume Parsing:** Upload your CV in PDF format and get it summarized by an LLM.
- **🤖 Smart AI Interviewer:** Contextual technical and HR questions based on your actual resume.
- **🎤 Voice & Text UI:** Real-time text-to-speech and WebSocket-powered chat for a seamless interview flow.
- **🕵️ Proctoring:** Modern webcam-based face capture and liveness via MediaPipe and OpenCV.
- **📝 Invisible AI Scoring:** Each answer is evaluated for communication, technical depth, and more (hidden from user).
- **✅ Interactive Reports:** Auto-generated PDF reports with KPIs, strengths, weaknesses, and violation logs.

---

## Installation

### 1. Set Up Python (Recommended: 3.10)

Make sure you have Python 3.10 installed.

### 2. Clone This Repository

git clone https://github.com/yourusername/interview-bot.git
cd interview-bot


### 3. (For macOS) Install System Dependencies


### 4. Create and Activate a Virtual Environment


### 5. Install Python Dependencies


### 6. Configure API Keys

- Copy `.env.template` to `.env`, and add your actual OpenRouter API key:


---

## Usage

1. **Start the FastAPI app:**


2. Open `http://localhost:8000/` in your browser.


3. **App Flow:**
 1. Fill out personal info and upload your resume (PDF).
 2. Continue to face verification and capture your reference face.
 3. The AI Interviewer begins via WebSocket.
 4. Answer questions (audio + text)—answers are scored silently.
 5. At the end, download your detailed PDF report.

---

## Project Structure

Interview_Bot/
├── app.py # Main FastAPI app (routes, LLM, workflow logic)
├── proctoring_service.py # MediaPipe/OpenCV proctoring and face analysis
├── static/ # CSS, JS, avatars, front-end resources
├── templates/ # Jinja2 HTML templates (index, report, etc.)
├── audio_files/ # Interview TTS MP3s
├── requirements.txt # Project dependencies
├── .env # NOT tracked; store your API keys here
├── .gitignore # Excludes venv, audio, pycache, etc.
└── README.md # This file



---

## Technical Details

- **Backend:** FastAPI, Python 3.10, Uvicorn, Jinja2
- **Frontend:** JS, HTML5, vanilla CSS
- **LLM Summarizer & QA:** OpenRouter (Gemini/free deepseek) API
- **Proctoring:** MediaPipe, OpenCV
- **Text-to-Speech:** gTTS
- **PDF Export:** WeasyPrint
- **Async:** ThreadPoolExecutor, asyncio for TTS and video analysis

---

## Configuration

**Environment variables (`.env`):**

OPENROUTER_API_KEY=your_openrouter_api_key_here


**Never commit `.env` (already in .gitignore).**

---

## Troubleshooting

- **PDF parsing slow or stuck?** Try smaller / text-only PDFs. See logs for extraction time.
- **AI summarizer slow?** Free OpenRouter models can take 30–90sec; try stubbing, as per docs.
- **Face or Proctoring issues?** Ensure webcam is enabled, dependencies are installed (`brew install ...`), and run from a clean terminal.
- **Server restarts after resume upload?** Avoid editing code files or running with `--reload` during an active flow.
- **Audio not playing?** Check browser support and permissions.

---

## Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) for the backend.
- [OpenRouter.ai](https://openrouter.ai/) for LLM APIs.
- [MediaPipe](https://mediapipe.dev/) & OpenCV for face analysis.
- [WeasyPrint](https://weasyprint.org/) for high-quality PDF export.
- [gTTS](https://pypi.org/project/gTTS/) for TTS.

---



