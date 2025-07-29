import os
import json
from PyPDF2 import PdfReader
from fastapi import FastAPI, Request, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import requests
from gtts import gTTS
from datetime import datetime
from typing import List, Dict
from pydantic import BaseModel
import uuid
import tempfile
import uvicorn
import logging
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from weasyprint import HTML, CSS
from io import BytesIO
import re
import os

os.environ["GLOG_minloglevel"] = "2"  # Hide MediaPipe startup dump

# Import the proctoring service
from proctoring_service import ProctoringService

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

AUDIO_FOLDER = "audio_files"
os.makedirs(AUDIO_FOLDER, exist_ok=True)

API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "deepseek/deepseek-r1-0528-qwen3-8b:free"

# Create a thread pool for blocking operations
executor = ThreadPoolExecutor(max_workers=4)

# Initialize proctoring service
proctoring_service = ProctoringService()

# --- PDF Parsing (pdfplumber) ---
def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        reader = PdfReader(pdf_path)
        text = []
        for page in reader.pages:
            extracted = page.extract_text() or ""
            text.append(extracted)
        return "\n".join(text).strip()
    except Exception as e:
        logger.error(f"Error during PyPDF2 text extraction: {e}")
        return ""

# --- Resume Summarization Function ---
async def summarize_resume(resume_text: str) -> str:
    """Generate a comprehensive summary of the resume once to reuse in all prompts."""
    prompt = f"""
You are a smart AI assistant. The following is a candidate's resume.

Your job is to extract and summarize all key elements: education, projects, internships, certifications, skills, achievements, tools, and any other relevant details.

Present them in a clean and complete paragraph format. This will be reused throughout the interview.

Resume:
--------
{resume_text}
"""
    try:
        summary = (await query_gemini(prompt)).strip()
        logger.info("Resume summarized successfully.")
        return summary
    except Exception as e:
        logger.error(f"Failed to summarize resume: {e}")
        return resume_text  # fallback to raw

# --- State management ---
# ADDED: User details model for face capture
class UserDetails(BaseModel):
    name: str = ""
    phone: str = ""
    email: str = ""

class InterviewState(BaseModel):
    user_details: UserDetails = UserDetails()  # ADDED
    resume_text: str = ""
    resume_summary: str = ""  # NEW: Store resume summary instead of full text
    current_dialogue: List[Dict] = []
    is_interview_active: bool = False
    current_question_count: int = 0
    max_questions: int = 7
    min_questions: int = 5
    last_question: str = ""
    consent_received: bool = False
    answer_evaluations: List[Dict] = []  # Store AI evaluations silently
    total_score: float = 0.0
    average_score: float = 0.0
    proctoring_session_id: str = ""  # Track proctoring session
    proctoring_violations: List[Dict] = []  # Track violations
    reference_face_captured: bool = False  # ADDED

class InterviewKPIs(BaseModel):
    communication_score: float = 0.0
    technical_score: float = 0.0
    problem_solving_score: float = 0.0
    confidence_score: float = 0.0
    clarity_score: float = 0.0
    response_time_avg: float = 0.0
    questions_answered: int = 0
    completion_rate: float = 0.0
    engagement_level: str = "Medium"
    strengths_count: int = 0
    improvement_areas_count: int = 0

class InterviewReport(BaseModel):
    candidate_name: str = "Candidate"
    candidate_phone: str = ""  # ADDED
    candidate_email: str = ""  # ADDED
    interview_date: str = ""
    overall_score: float = 0.0
    technical_score: float = 0.0
    communication_score: float = 0.0
    experience_score: float = 0.0
    problem_solving_score: float = 0.0
    detailed_feedback: str = ""
    resume_quality: str = ""
    technical_skills: str = ""
    communication_skills: str = ""
    strengths: List[str] = []
    areas_for_improvement: List[str] = []
    recommendations: str = ""
    interview_transcript: List[Dict] = []
    kpis: InterviewKPIs = InterviewKPIs()
    proctoring_violations: List[Dict] = []  # Add proctoring violations

interview_state = InterviewState()
logger.info("InterviewState initialized.")

# Global variable to store generated reports
generated_reports = {}

# ADDED: Simple storage for user details (for production, use a proper database)
user_sessions = {}

# --- WebSocket manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.proctoring_connections: List[WebSocket] = []
        logger.info("ConnectionManager initialized.")

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected: {websocket.client}")

    async def connect_proctoring(self, websocket: WebSocket):
        await websocket.accept()
        self.proctoring_connections.append(websocket)
        logger.info(f"Proctoring WebSocket connected: {websocket.client}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected: {websocket.client}")

    def disconnect_proctoring(self, websocket: WebSocket):
        if websocket in self.proctoring_connections:
            self.proctoring_connections.remove(websocket)
        logger.info(f"Proctoring WebSocket disconnected: {websocket.client}")

manager = ConnectionManager()

# --- Async Audio Generation ---
async def generate_audio_async(text: str, lang: str = 'en') -> str:
    """Generate audio asynchronously using thread pool"""
    filename = f"audio_{uuid.uuid4().hex}.mp3"
    filepath = os.path.join(AUDIO_FOLDER, filename)

    def _generate_audio():
        for attempt in range(3):
            try:
                tts = gTTS(text=text, lang=lang)
                tts.save(filepath)
                logger.info(f"Audio generated successfully: {filename}")
                return filename
            except Exception as e:
                logger.warning(f"[gTTS] Attempt {attempt + 1} failed: {e}")
                if attempt == 2:
                    raise e
                time.sleep(2)

    # Run gTTS in thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    filename = await loop.run_in_executor(executor, _generate_audio)
    return filename

# Legacy function for backward compatibility
def generate_audio(text: str, lang: str = 'en') -> str:
    filename = f"audio_{uuid.uuid4().hex}.mp3"
    filepath = os.path.join(AUDIO_FOLDER, filename)

    for attempt in range(3):
        try:
            tts = gTTS(text=text, lang=lang)
            tts.save(filepath)
            logger.info(f"Audio generated successfully: {filename}")
            return filename
        except Exception as e:
            logger.warning(f"[gTTS] Attempt {attempt + 1} failed: {e}")
            time.sleep(2)

    logger.error("gTTS failed after 3 retries.")
    raise Exception("gTTS failed after 3 retries")

async def query_gemini(prompt: str) -> str:
    logger.info(f"Querying Gemini (via OpenRouter) with prompt: {prompt[:500]}...")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a professional AI interviewer."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.9,
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        logger.info("Gemini query successful.")
        return content
    except requests.exceptions.RequestException as e:
        logger.error(f"Error querying Gemini API (OpenRouter): {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in query_gemini: {e}")
        raise

async def generate_introductory_question(resume_summary: str) -> str:
    """Always start with this fixed question after consent."""
    return "Tell me about yourself."

# Global state for tracking
current_topic = None
topic_question_count = 0
covered_topics = set()

async def generate_dynamic_question(resume_summary: str, last_response: str, dialogue: List[Dict]) -> str:
    global current_topic, topic_question_count, covered_topics

    # Get recent conversation context (last 4 exchanges)
    recent_context = "\n".join(
        f"{msg['role']}: {msg['content']}" for msg in dialogue[-4:]
    )

    prompt = f"""Candidate Summary (from resume):
--------
{resume_summary}

Recent conversation:
{recent_context}

Last answer: {last_response}

Topics already covered: {', '.join(covered_topics) if covered_topics else 'None'}

Generate ONE interview question following these rules:

1. Focus on: projects, internships, certifications, technical skills, tools used
2. If last answer was detailed and complete → move to NEW topic from resume
3. If last answer was brief/incomplete → ask ONE follow-up, then move on
4. Don't repeat covered topics: {covered_topics}
5. Prioritize: projects > internships > certifications > skills
6. Ask specific technical questions about implementation, challenges, results

Return ONLY the question. No explanations."""

    try:
        question = (await query_gemini(prompt)).strip()

        # Simple topic management
        followup_keywords = ["how", "what", "can you elaborate", "tell me more", "explain"]
        is_followup = any(keyword in question.lower()[:20] for keyword in followup_keywords)

        if is_followup and current_topic:
            topic_question_count += 1
            if topic_question_count >= 2:  # Max 2 questions per topic
                covered_topics.add(current_topic)
                current_topic = None
                topic_question_count = 0
        else:
            # New topic detected
            if current_topic:
                covered_topics.add(current_topic)
            current_topic = extract_topic_from_question(question)
            topic_question_count = 1

        return question

    except Exception as e:
        logger.error(f"Error generating question: {e}")
        return get_fallback_question()

def extract_topic_from_question(question: str) -> str:
    """Extract main topic from question for tracking"""
    question_lower = question.lower()

    # Topic keywords mapping
    topics = {
        'project': ['project', 'application', 'system', 'built', 'developed'],
        'internship': ['internship', 'intern', 'company', 'workplace'],
        'certification': ['certification', 'certified', 'course', 'training'],
        'skills': ['technology', 'language', 'framework', 'tool', 'skill']
    }

    for topic, keywords in topics.items():
        if any(keyword in question_lower for keyword in keywords):
            return topic
    return 'general'

def get_fallback_question() -> str:
    """Simple fallback questions covering main resume areas"""
    fallbacks = [
        "What's the most challenging project you've worked on?",
        "Tell me about your internship experience and key learnings.",
        "Which certification or course has been most valuable to you?",
        "What technologies are you most comfortable working with?"
    ]

    return fallbacks[len(covered_topics) % len(fallbacks)]

# Reset function for new interviews
def reset_interview_state():
    global current_topic, topic_question_count, covered_topics
    current_topic = None
    topic_question_count = 0
    covered_topics = set()

async def evaluate_user_answer(question: str, user_answer: str, resume_summary: str) -> Dict:
    """Evaluate user's answer in real-time and provide detailed feedback."""
    prompt = f"""
You are an expert interview evaluator. Analyze this candidate's response to an interview question.

QUESTION ASKED:
{question}

CANDIDATE'S ANSWER:
{user_answer}

CANDIDATE'S RESUME CONTEXT:
{resume_summary}

Provide evaluation in this EXACT format:

SCORE: [0-10]
TECHNICAL_ACCURACY: [Rate technical correctness 0-10]
COMMUNICATION_CLARITY: [Rate clarity and articulation 0-10]
RELEVANCE: [Rate how well answer addresses question 0-10]
DEPTH: [Rate depth of explanation 0-10]
CONFIDENCE: [Rate confidence level 0-10]
PROBLEM_SOLVING: [Rate problem-solving approach 0-10]
STRENGTHS: [List 2-3 key strengths in the answer]
WEAKNESSES: [List 2-3 areas for improvement]
FEEDBACK: [Constructive feedback in 2-3 sentences]
FOLLOW_UP_SUGGESTION: [Suggest what interviewer should ask next based on this answer]

Evaluation Criteria:
- Technical Accuracy (20%): Correctness of technical information
- Communication Clarity (20%): Clear articulation and professional presentation
- Relevance (20%): How well the answer addresses the specific question
- Depth (20%): Level of detail and insight provided
- Confidence (10%): Confidence in delivery and knowledge
- Problem-Solving (10%): Approach to solving problems

Provide specific, actionable feedback that helps the candidate improve.
"""

    try:
        evaluation = await query_gemini(prompt)

        # Extract evaluation components using regex
        score_match = re.search(r'SCORE:\s*(\d+(?:\.\d+)?)', evaluation, re.IGNORECASE)
        tech_match = re.search(r'TECHNICAL_ACCURACY:\s*(\d+(?:\.\d+)?)', evaluation, re.IGNORECASE)
        comm_match = re.search(r'COMMUNICATION_CLARITY:\s*(\d+(?:\.\d+)?)', evaluation, re.IGNORECASE)
        rel_match = re.search(r'RELEVANCE:\s*(\d+(?:\.\d+)?)', evaluation, re.IGNORECASE)
        depth_match = re.search(r'DEPTH:\s*(\d+(?:\.\d+)?)', evaluation, re.IGNORECASE)
        conf_match = re.search(r'CONFIDENCE:\s*(\d+(?:\.\d+)?)', evaluation, re.IGNORECASE)
        prob_match = re.search(r'PROBLEM_SOLVING:\s*(\d+(?:\.\d+)?)', evaluation, re.IGNORECASE)

        # Extract scores with validation
        overall_score = float(score_match.group(1)) if score_match else 5.0
        technical_score = float(tech_match.group(1)) if tech_match else 5.0
        communication_score = float(comm_match.group(1)) if comm_match else 5.0
        relevance_score = float(rel_match.group(1)) if rel_match else 5.0
        depth_score = float(depth_match.group(1)) if depth_match else 5.0
        confidence_score = float(conf_match.group(1)) if conf_match else 5.0
        problem_solving_score = float(prob_match.group(1)) if prob_match else 5.0

        # Extract text sections
        strengths = extract_section(evaluation, 'STRENGTHS', 'WEAKNESSES')
        weaknesses = extract_section(evaluation, 'WEAKNESSES', 'FEEDBACK')
        feedback = extract_section(evaluation, 'FEEDBACK', 'FOLLOW_UP_SUGGESTION')
        follow_up_suggestion = extract_section(evaluation, 'FOLLOW_UP_SUGGESTION', None)

        return {
            "overall_score": min(10.0, max(0.0, overall_score)),
            "technical_accuracy": min(10.0, max(0.0, technical_score)),
            "communication_clarity": min(10.0, max(0.0, communication_score)),
            "relevance": min(10.0, max(0.0, relevance_score)),
            "depth": min(10.0, max(0.0, depth_score)),
            "confidence": min(10.0, max(0.0, confidence_score)),
            "problem_solving": min(10.0, max(0.0, problem_solving_score)),
            "strengths": strengths,
            "weaknesses": weaknesses,
            "feedback": feedback,
            "follow_up_suggestion": follow_up_suggestion,
            "raw_evaluation": evaluation
        }

    except Exception as e:
        logger.error(f"Error evaluating answer: {e}")
        return {
            "overall_score": 5.0,
            "technical_accuracy": 5.0,
            "communication_clarity": 5.0,
            "relevance": 5.0,
            "depth": 5.0,
            "confidence": 5.0,
            "problem_solving": 5.0,
            "strengths": "Response provided",
            "weaknesses": "Evaluation temporarily unavailable",
            "feedback": "Please continue with the interview",
            "follow_up_suggestion": "Ask a follow-up question based on the response",
            "raw_evaluation": "Evaluation failed"
        }

def extract_section(text: str, start_marker: str, end_marker: str = None) -> str:
    """Extract text section between markers."""
    start_pattern = rf'{re.escape(start_marker)}:\s*'
    start_match = re.search(start_pattern, text, re.IGNORECASE)
    
    if not start_match:
        return "Not available"
    
    start_pos = start_match.end()
    
    if end_marker:
        end_pattern = rf'{re.escape(end_marker)}:'
        end_match = re.search(end_pattern, text[start_pos:], re.IGNORECASE)
        if end_match:
            return text[start_pos:start_pos + end_match.start()].strip()
    
    return text[start_pos:].strip()

def calculate_kpis(evaluations: List[Dict]) -> InterviewKPIs:
    """Calculate KPIs from evaluation data."""
    if not evaluations:
        return InterviewKPIs()

    # Calculate average scores
    communication_scores = [eval_data["evaluation"]["communication_clarity"] for eval_data in evaluations]
    technical_scores = [eval_data["evaluation"]["technical_accuracy"] for eval_data in evaluations]
    problem_solving_scores = [eval_data["evaluation"].get("problem_solving", 5.0) for eval_data in evaluations]
    confidence_scores = [eval_data["evaluation"].get("confidence", 5.0) for eval_data in evaluations]

    # Calculate averages
    communication_avg = sum(communication_scores) / len(communication_scores)
    technical_avg = sum(technical_scores) / len(technical_scores)
    problem_solving_avg = sum(problem_solving_scores) / len(problem_solving_scores)
    confidence_avg = sum(confidence_scores) / len(confidence_scores)

    # Calculate completion rate
    expected_questions = interview_state.max_questions
    actual_questions = len(evaluations)
    completion_rate = (actual_questions / expected_questions) * 100

    # Determine engagement level
    overall_avg = (communication_avg + technical_avg + problem_solving_avg + confidence_avg) / 4
    if overall_avg >= 8:
        engagement_level = "High"
    elif overall_avg >= 6:
        engagement_level = "Medium"
    else:
        engagement_level = "Low"

    # Count strengths and improvement areas
    strengths_count = sum(1 for eval_data in evaluations if eval_data["evaluation"]["strengths"] != "Not available")
    improvement_areas_count = sum(1 for eval_data in evaluations if eval_data["evaluation"]["weaknesses"] != "Not available")

    return InterviewKPIs(
        communication_score=communication_avg,
        technical_score=technical_avg,
        problem_solving_score=problem_solving_avg,
        confidence_score=confidence_avg,
        clarity_score=communication_avg,  # Using communication as clarity proxy
        response_time_avg=0.0,  # Would need timing data
        questions_answered=actual_questions,
        completion_rate=completion_rate,
        engagement_level=engagement_level,
        strengths_count=strengths_count,
        improvement_areas_count=improvement_areas_count
    )

async def generate_interview_report(dialogue: List[Dict], resume_summary: str, evaluations: List[Dict]) -> InterviewReport:
    """Generate comprehensive report including AI evaluations and KPIs."""
    # Filter valid dialogue entries
    valid_dialogue = [
        msg for msg in dialogue
        if msg.get("content") and msg["content"] != "[No response]" and len(msg["content"].strip()) > 3
    ]

    # Calculate KPIs
    kpis = calculate_kpis(evaluations)

    # Calculate evaluation statistics
    if evaluations:
        overall_scores = [eval_data["evaluation"]["overall_score"] for eval_data in evaluations]
        technical_scores = [eval_data["evaluation"]["technical_accuracy"] for eval_data in evaluations]
        communication_scores = [eval_data["evaluation"]["communication_clarity"] for eval_data in evaluations]

        avg_overall = sum(overall_scores) / len(overall_scores)
        avg_technical = sum(technical_scores) / len(technical_scores)
        avg_communication = sum(communication_scores) / len(communication_scores)

        # Create detailed evaluation summary
        detailed_evaluations = "\n\n".join([
            f"Q{i+1}: {eval_data['question']}\n"
            f"Answer: {eval_data['answer'][:200]}{'...' if len(eval_data['answer']) > 200 else ''}\n"
            f"Score: {eval_data['evaluation']['overall_score']}/10\n"
            f"Communication: {eval_data['evaluation']['communication_clarity']}/10\n"
            f"Technical: {eval_data['evaluation']['technical_accuracy']}/10\n"
            f"Confidence: {eval_data['evaluation'].get('confidence', 5.0)}/10\n"
            f"Feedback: {eval_data['evaluation']['feedback']}\n"
            f"Strengths: {eval_data['evaluation']['strengths']}\n"
            f"Areas for Improvement: {eval_data['evaluation']['weaknesses']}"
            for i, eval_data in enumerate(evaluations)
        ])

        # Extract strengths and areas for improvement
        strengths = [eval_data["evaluation"]["strengths"] for eval_data in evaluations if eval_data["evaluation"]["strengths"] != "Not available"]
        areas_for_improvement = [eval_data["evaluation"]["weaknesses"] for eval_data in evaluations if eval_data["evaluation"]["weaknesses"] != "Not available"]

    else:
        avg_overall = 0.0
        avg_technical = 0.0
        avg_communication = 0.0
        detailed_evaluations = "No evaluations available"
        strengths = []
        areas_for_improvement = []

    # Generate overall analysis
    dialogue_text = "\n".join([
        f"{msg['role'].capitalize()}: {msg['content']}"
        for msg in valid_dialogue
    ])

    prompt = f"""
Generate a comprehensive interview analysis based on the following data:

RESUME SUMMARY: {resume_summary}

INTERVIEW TRANSCRIPT: {dialogue_text}

AI EVALUATION SUMMARY: {detailed_evaluations}

Provide detailed analysis covering overall performance, technical skills, communication abilities, and recommendations.
Focus on constructive feedback and specific areas for improvement.
"""

    try:
        analysis = await query_gemini(prompt)

        report = InterviewReport(
            candidate_name=interview_state.user_details.name or "Candidate",
            candidate_phone=interview_state.user_details.phone,
            candidate_email=interview_state.user_details.email,
            interview_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            overall_score=avg_overall * 10,  # Convert to 0-100 scale
            technical_score=avg_technical * 10,
            communication_score=avg_communication * 10,
            detailed_feedback=f"Real-time AI Evaluations:\n\n{detailed_evaluations}\n\n"
                            f"Overall Analysis:\n{analysis}",
            strengths=strengths[:5],  # Limit to top 5
            areas_for_improvement=areas_for_improvement[:5],  # Limit to top 5
            interview_transcript=valid_dialogue,  # Use filtered dialogue
            kpis=kpis,
            proctoring_violations=interview_state.proctoring_violations
        )

        return report

    except Exception as e:
        logger.error(f"Error generating report: {e}")
        return InterviewReport(
            candidate_name=interview_state.user_details.name or "Candidate",
            candidate_phone=interview_state.user_details.phone,
            candidate_email=interview_state.user_details.email,
            interview_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            overall_score=avg_overall * 10,
            technical_score=avg_technical * 10,
            communication_score=avg_communication * 10,
            detailed_feedback=f"Real-time AI Evaluations:\n\n{detailed_evaluations}",
            strengths=strengths[:5],
            areas_for_improvement=areas_for_improvement[:5],
            interview_transcript=valid_dialogue,
            kpis=kpis,
            proctoring_violations=interview_state.proctoring_violations
        )

async def generate_report_background(dialogue: List[Dict], resume_summary: str, evaluations: List[Dict], session_id: str):
    """Generate report in background without blocking WebSocket"""
    try:
        report = await generate_interview_report(dialogue, resume_summary, evaluations)
        generated_reports[session_id] = report
        logger.info(f"Report generated for session {session_id}")
    except Exception as e:
        logger.error(f"Background report generation failed: {e}")

# --- Routes ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    logger.info("Serving index page.")
    global interview_state
    interview_state = InterviewState()
    return templates.TemplateResponse("index.html", {"request": request, "report": None})

@app.post("/start_interview")
async def start_interview(
    request: Request,
    resume: List[UploadFile] = File(...),
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...)
):
    logger.info("Starting new interview process.")
    global interview_state

    # Reset state completely
    interview_state.user_details = UserDetails(name=name, phone=phone, email=email)
    interview_state.resume_text = ""
    interview_state.resume_summary = ""  # Clear previous summary
    interview_state.current_dialogue = []
    interview_state.is_interview_active = False
    interview_state.current_question_count = 0
    interview_state.last_question = ""
    interview_state.consent_received = False
    interview_state.answer_evaluations = []
    interview_state.total_score = 0.0
    interview_state.average_score = 0.0
    interview_state.proctoring_session_id = str(uuid.uuid4())
    interview_state.proctoring_violations = []
    interview_state.reference_face_captured = False

    if not resume:
        logger.warning("No resume file uploaded.")
        raise HTTPException(status_code=400, detail="No resume file uploaded.")

    for file in resume:
        if not file.filename.endswith(".pdf"):
            logger.warning(f"Uploaded file is not a PDF: {file.filename}")
            raise HTTPException(status_code=400, detail="Only PDF resumes are supported.")

        contents = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        extracted_text = extract_text_from_pdf(tmp_path)
        logger.info(f"Extracted text from {file.filename}. Length: {len(extracted_text)}")
        interview_state.resume_text += extracted_text + "\n"

        os.unlink(tmp_path)

    if not interview_state.resume_text.strip():
        logger.warning("Unable to extract text from resume.")
        raise HTTPException(status_code=400, detail="Unable to extract text from resume.")

    # NEW: Generate resume summary once
    interview_state.resume_summary = await summarize_resume(interview_state.resume_text)
    logger.info(f"Resume summary generated. Length: {len(interview_state.resume_summary)}")

    # Store user session data
    session_data = {
        "user_details": interview_state.user_details.dict(),
        "proctoring_session_id": interview_state.proctoring_session_id,
        "created_at": datetime.now().isoformat()
    }

    user_sessions[interview_state.proctoring_session_id] = session_data

    # Initialize proctoring session
    await proctoring_service.create_session(interview_state.proctoring_session_id)

    logger.info(f"Interview initialized for {name}. Awaiting face verification.")
    return JSONResponse({
        "status": "ready_for_face_capture",
        "message": "Please proceed to face verification.",
        "proctoring_session_id": interview_state.proctoring_session_id,
        "user_name": name
    })

@app.post("/capture_reference_face")
async def capture_reference_face(request: Request):
    """Store the captured reference face for identity verification."""
    try:
        data = await request.json()
        image_data = data.get('image_data')

        if not image_data:
            raise HTTPException(status_code=400, detail="No image data provided")

        # Set reference face in proctoring service
        result = await proctoring_service.set_reference_face(
            interview_state.proctoring_session_id,
            image_data
        )

        if result.get('status') == 'success':
            interview_state.reference_face_captured = True
            logger.info("Reference face captured successfully")
            return JSONResponse({
                "status": "success",
                "message": "Reference face captured successfully"
            })
        else:
            # Still allow interview to proceed even if face capture fails
            interview_state.reference_face_captured = True
            logger.warning("Face capture failed but allowing interview to proceed")
            return JSONResponse({
                "status": "success",
                "message": "Session activated successfully"
            })

    except Exception as e:
        logger.error(f"Error capturing reference face: {e}")
        # Fallback: Still allow interview to proceed
        interview_state.reference_face_captured = True
        return JSONResponse({
            "status": "success",
            "message": "Session activated successfully"
        })

@app.get("/user_session/{session_id}")
async def get_user_session(session_id: str):
    """Get user session data."""
    if session_id in user_sessions:
        return JSONResponse(user_sessions[session_id])
    else:
        raise HTTPException(status_code=404, detail="Session not found")

@app.post("/start_interview_session")
async def start_interview_session():
    """Start the actual interview session after face verification."""
    try:
        # Allow interview to proceed regardless of face capture status
        interview_state.is_interview_active = True
        logger.info("Interview session started.")

        return JSONResponse({
            "status": "interview_ready",
            "message": "Interview session ready. Please connect to WebSocket to begin.",
            "proctoring_session_id": interview_state.proctoring_session_id
        })

    except Exception as e:
        logger.error(f"Error starting interview session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/interview")
async def websocket_interview(websocket: WebSocket):
    logger.info(f"WebSocket interview connection established for {websocket.client}")
    await manager.connect(websocket)

    # Send initial greeting only once
    greeting = "I'm an AI interviewer. I'm here to conduct a technical interview with you. Are you ready to begin?"

    interview_state.current_dialogue.append({
        "role": "interviewer",
        "content": greeting,
        "timestamp": datetime.now().isoformat()
    })

    interview_state.last_question = greeting

    # Generate audio asynchronously
    audio_filename = await generate_audio_async(greeting)

    await websocket.send_text(json.dumps({
        "type": "question",
        "content": greeting,
        "audio_file": audio_filename,
        "start_recording": True,
        "proctoring_session_id": interview_state.proctoring_session_id
    }))

    logger.info("Initial greeting sent via WebSocket")

    while interview_state.is_interview_active:
        try:
            data = await websocket.receive()
            if 'text' not in data:
                continue

            message = json.loads(data['text'])
            logger.debug(f"Received message type: {message.get('type')}")

            if message['type'] == 'text_response':
                user_text = message['content'].strip()
                logger.info(f"User response: {user_text[:50]}...")

                # Only process non-empty responses
                if not user_text or user_text == "[No response]":
                    logger.warning("Empty response received, requesting user to try again")
                    await websocket.send_text(json.dumps({
                        "type": "question",
                        "content": "I didn't catch that. Could you please repeat your answer?",
                        "audio_file": await generate_audio_async("I didn't catch that. Could you please repeat your answer?"),
                        "start_recording": True
                    }))
                    continue

                # Send simple acknowledgment without evaluation details
                await websocket.send_text(json.dumps({
                    "type": "processing_response",
                    "content": "Thank you for your response. Processing next question..."
                }))

                # Process user response
                interview_state.current_dialogue.append({
                    "role": "candidate",
                    "content": user_text,
                    "timestamp": datetime.now().isoformat()
                })

                # Consent flow
                if not interview_state.consent_received:
                    if any(kw in user_text.lower() for kw in ["yes", "sure", "ready", "start", "okay", "go ahead", "begin"]):
                        interview_state.consent_received = True
                        logger.info("Consent received. Asking 'Tell me about yourself'")

                        first_question = await generate_introductory_question(interview_state.resume_summary)
                        interview_state.current_question_count += 1
                        interview_state.last_question = first_question

                        interview_state.current_dialogue.append({
                            "role": "interviewer",
                            "content": first_question,
                            "timestamp": datetime.now().isoformat()
                        })

                        audio_filename = await generate_audio_async(first_question)

                        await websocket.send_text(json.dumps({
                            "type": "question",
                            "content": first_question,
                            "audio_file": audio_filename,
                            "start_recording": True
                        }))
                    else:
                        await websocket.send_text(json.dumps({
                            "type": "question",
                            "content": "Just let me know when you're ready to begin the interview.",
                            "audio_file": await generate_audio_async("Just let me know when you're ready to begin the interview."),
                            "start_recording": True
                        }))
                    continue

                # **HIDDEN AI EVALUATION - Store but don't show**
                if user_text.strip() and interview_state.last_question:
                    try:
                        # Run evaluation silently in background using resume summary
                        evaluation = await evaluate_user_answer(
                            interview_state.last_question,
                            user_text,
                            interview_state.resume_summary  # Use summary instead of full text
                        )

                        # Store evaluation silently for report generation
                        interview_state.answer_evaluations.append({
                            "question": interview_state.last_question,
                            "answer": user_text,
                            "evaluation": evaluation,
                            "timestamp": datetime.now().isoformat()
                        })

                        # Update running scores silently
                        interview_state.total_score += evaluation["overall_score"]
                        interview_state.average_score = interview_state.total_score / len(interview_state.answer_evaluations)

                        logger.info(f"Answer evaluated silently: Score {evaluation['overall_score']}/10, Average: {interview_state.average_score:.1f}")

                        # NO FEEDBACK SENT TO USER - keep evaluation hidden

                    except Exception as e:
                        logger.error(f"Error during silent answer evaluation: {e}")

                # UPDATED: Reduced wait time
                await asyncio.sleep(1)

                should_continue = interview_state.current_question_count < interview_state.max_questions

                if should_continue:
                    next_question = await generate_dynamic_question(
                        interview_state.resume_summary,  # Use summary instead of full text
                        user_text,
                        interview_state.current_dialogue
                    )

                    # If Gemini returns thank-you (i.e., it thinks interview is over)
                    if "thank you for attending" in next_question.lower():
                        should_continue = False
                else:
                    next_question = "Thank you for attending the interview. Your report will be generated shortly."
                    should_continue = False

                interview_state.current_question_count += 1
                interview_state.last_question = next_question

                interview_state.current_dialogue.append({
                    "role": "interviewer",
                    "content": next_question,
                    "timestamp": datetime.now().isoformat()
                })

                audio_filename = await generate_audio_async(next_question)

                await websocket.send_text(json.dumps({
                    "type": "question" if should_continue else "interview_concluded",
                    "content": next_question,
                    "audio_file": audio_filename,
                    "start_recording": should_continue,
                    "stop_recording": not should_continue,
                    "total_questions": len(interview_state.answer_evaluations)
                }))

                if not should_continue:
                    break

            elif message['type'] == 'end_interview':
                logger.info("Client requested to end interview.")
                conclusion = "Thank you for your time. Your interview report will be available shortly."

                interview_state.current_dialogue.append({
                    "role": "interviewer",
                    "content": conclusion,
                    "timestamp": datetime.now().isoformat()
                })

                audio_filename = await generate_audio_async(conclusion)

                await websocket.send_text(json.dumps({
                    "type": "interview_concluded",
                    "content": conclusion,
                    "audio_file": audio_filename,
                    "stop_recording": True
                }))
                break

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for {websocket.client}.")
            break
        except Exception as e:
            logger.error(f"Error processing WebSocket message for {websocket.client}: {e}", exc_info=True)
            await websocket.send_text(json.dumps({
                "type": "error",
                "content": "Sorry, something went wrong. Let's continue shortly.",
                "stop_recording": True
            }))
            break

    manager.disconnect(websocket)
    interview_state.is_interview_active = False
    
    # NEW: Clear resume data after interview ends to free memory
    interview_state.resume_text = ""
    interview_state.resume_summary = ""
    
    logger.info(f"Interview for {websocket.client} concluded and state reset.")

@app.websocket("/ws/proctoring")
async def websocket_proctoring(websocket: WebSocket):
    """WebSocket endpoint for proctoring functionality"""
    logger.info(f"Proctoring WebSocket connection established for {websocket.client}")
    await manager.connect_proctoring(websocket)

    while True:
        try:
            data = await websocket.receive()
            if 'text' not in data:
                continue

            message = json.loads(data['text'])
            logger.debug(f"Received proctoring message type: {message.get('type')}")

            if message['type'] == 'set_reference_face':
                result = await proctoring_service.set_reference_face(
                    message['session_id'],
                    message['image_data']
                )

                await websocket.send_text(json.dumps({
                    "type": "reference_face_response",
                    "result": result
                }))

            elif message['type'] == 'process_frame':
                result = await proctoring_service.process_frame(
                    message['session_id'],
                    message['image_data']
                )

                # Store violations in interview state
                if result.get('violations'):
                    for violation in result['violations']:
                        if violation.get('type') == 'violation':
                            interview_state.proctoring_violations.append({
                                "timestamp": datetime.now().isoformat(),
                                "type": violation.get('message', 'Unknown violation'),
                                "severity": violation.get('severity', 'medium')
                            })

                # Check if session should be terminated
                if result.get('violations'):
                    for violation in result['violations']:
                        if violation.get('terminate', False):
                            # End interview due to proctoring violations
                            interview_state.is_interview_active = False
                            logger.info("Interview terminated due to proctoring violations")
                            break

                await websocket.send_text(json.dumps({
                    "type": "proctoring_result",
                    "result": result
                }))

        except WebSocketDisconnect:
            logger.info(f"Proctoring WebSocket disconnected for {websocket.client}.")
            break
        except Exception as e:
            logger.error(f"Error processing proctoring WebSocket message: {e}", exc_info=True)
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Proctoring error occurred"
            }))
            break

    manager.disconnect_proctoring(websocket)

@app.get("/report", response_class=HTMLResponse)
async def get_report(request: Request):
    """Generate and display the interview report."""
    global interview_state

    if not interview_state.current_dialogue:
        logger.warning("No interview data available for report generation")
        return templates.TemplateResponse("index.html", {
            "request": request,
            "error": "No interview data available. Please complete an interview first."
        })

    # End proctoring session if active
    if interview_state.proctoring_session_id:
        await proctoring_service.end_session(interview_state.proctoring_session_id)

    # Generate the comprehensive report using resume summary
    report = await generate_interview_report(
        interview_state.current_dialogue,
        interview_state.resume_summary,  # Use summary instead of full text
        interview_state.answer_evaluations
    )

    return templates.TemplateResponse("report.html", {
        "request": request,
        "report": report
    })

@app.get("/report/download")
async def download_report_pdf(request: Request):
    """Generate and download PDF report."""
    global interview_state

    if not interview_state.current_dialogue:
        raise HTTPException(status_code=404, detail="No interview data available")

    # Generate the report using resume summary
    report = await generate_interview_report(
        interview_state.current_dialogue,
        interview_state.resume_summary,  # Use summary instead of full text
        interview_state.answer_evaluations
    )

    # Render HTML template
    html_content = templates.get_template("report_pdf.html").render(
        request=request,
        report=report
    )

    # Generate PDF
    pdf_buffer = BytesIO()
    HTML(string=html_content).write_pdf(pdf_buffer)
    pdf_buffer.seek(0)

    return Response(
        content=pdf_buffer.read(),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=interview_report.pdf"}
    )

@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    logger.info(f"Serving audio file: {filename}")
    file_path = os.path.join(AUDIO_FOLDER, filename)

    if not os.path.exists(file_path):
        logger.error(f"Audio file not found: {file_path}")
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(file_path)

if __name__ == "__main__":
    logger.info("Starting FastAPI application with Uvicorn.")
    uvicorn.run(app, host="0.0.0.0", port=8020, reload=True)
