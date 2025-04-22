from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth, OAuthError
from dotenv import load_dotenv
import os
import logging

# Load .env into os.environ
load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "quiz-app-session-secret-key")
)

# OAuth setup
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

# Templates & static
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Auth helper
def is_authenticated(request: Request):
    return "user" in request.session

# Routes

@app.get("/", response_class=HTMLResponse)
async def welcome(request: Request):
    logger.info("Welcome page accessed")
    return templates.TemplateResponse("welcome.html", {"request": request})

@app.get("/quiz", response_class=HTMLResponse)
async def quiz(request: Request):
    logger.info("Quiz page accessed")
    # Static 3‑question general knowledge quiz
    quiz_data = {
        "title": "General Knowledge Quiz",
        "questions": [
            {"id": "q0", "text": "What is the capital of France?", "options": ["Berlin","Madrid","Paris","Rome"]},
            {"id": "q1", "text": "What is 2 + 2?",          "options": ["3","4","5","6"]},
            {"id": "q2", "text": "Which planet is known as the Red Planet?", "options": ["Earth","Mars","Jupiter","Venus"]},
        ]
    }
    return templates.TemplateResponse("quiz.html", {"request": request, "quiz": quiz_data})

@app.post("/submit-quiz")
async def submit_quiz(request: Request):
    form = await request.form()
    # store answers in session
    request.session['quiz_answers'] = {k: v for k, v in form.items() if k.startswith("q")}
    # then redirect into auth flow
    return RedirectResponse("/auth", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/auth", response_class=HTMLResponse)
async def auth(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/profile", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("auth.html", {"request": request})

@app.get("/auth/google")
async def login(request: Request):
    redirect_uri = request.url_for('auth_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        userinfo = token.get('userinfo')
        request.session['user'] = {
            "id": userinfo["sub"],
            "email": userinfo["email"],
            "name": userinfo["name"]
        }
    except OAuthError as e:
        logger.error(f"OAuth error: {e}")
        return RedirectResponse("/auth", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse("/profile", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/profile", response_class=HTMLResponse)
async def profile(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/auth", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": request.session['user'],
            "subject": request.session.get('selected_subject'),
            "topic": request.session.get('selected_topic')
        }
    )

@app.get("/subjects", response_class=HTMLResponse)
async def subjects(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/auth", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("subjects.html", {"request": request})

@app.post("/select-subject")
async def select_subject(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/auth", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    subject = form.get("subject")
    if subject not in {"math", "english"}:
        raise HTTPException(400, "Invalid subject")
    request.session['selected_subject'] = subject
    return RedirectResponse("/topics", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/topics", response_class=HTMLResponse)
async def topics(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/auth", status_code=status.HTTP_303_SEE_OTHER)
    subj = request.session.get('selected_subject')
    if not subj:
        return RedirectResponse("/subjects", status_code=status.HTTP_303_SEE_OTHER)
    topics_map = {
        "math":    ["set","equations","trigonometry","algebra","geometry"],
        "english": ["article","sentence","parts of speech","phrase","words"]
    }
    return templates.TemplateResponse(
        "topics.html",
        {"request": request, "subject": subj, "topics": topics_map[subj]}
    )

@app.post("/select-topic")
async def select_topic(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/auth", status_code=status.HTTP_303_SEE_OTHER)
    form = await request.form()
    topic = form.get("topic")
    if not topic:
        raise HTTPException(400, "No topic chosen")
    request.session['selected_topic'] = topic
    return RedirectResponse("/profile", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
