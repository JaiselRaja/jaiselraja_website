import os
import secrets
import base64
import re
from fastapi import FastAPI, Depends, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from database import engine, Base, get_db
import models

# Create tables if not exists
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Jaisel's Profile")

# Mount static directory for CSS and uploaded files
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

def get_drive_download_link(url: str) -> str:
    # Match standard drive links: https://drive.google.com/file/d/FILE_ID/view
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
    if match:
        return f"https://drive.google.com/uc?export=download&id={match.group(1)}"
    return url

templates.env.globals['get_download_link'] = get_drive_download_link

security = HTTPBasic()

# Setup Admin Credentials
# In production, use environment variables.
ADMIN_USERNAME = "jaisel"
ADMIN_PASSWORD = "password123"

def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

def check_is_admin(request: Request) -> bool:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
        username, password = decoded.split(":", 1)
        return secrets.compare_digest(username, ADMIN_USERNAME) and secrets.compare_digest(password, ADMIN_PASSWORD)
    except Exception:
        return False

TOPIC_MAP = {
    "Physics": [
        "Electrostatics",
        "Current Electricity",
        "Magnetism and Magnetic Effects of Electric Current",
        "Electromagnetic Induction and Alternating Current",
        "Electromagnetic Waves",
        "Ray Optics",
        "Wave Optics",
        "Dual Nature of Radiation and Matter",
        "Atomic and Nuclear Physics",
        "Electronics and Communication",
        "Recent Developments in Physics"
    ],
    "Chemistry": [
        "Metallurgy",
        "P-Block Elements - I",
        "P-Block Elements - II",
        "Transition and Inner Transition Elements",
        "Coordination Chemistry",
        "Solid State",
        "Chemical Kinetics",
        "Ionic Equilibrium",
        "Electro Chemistry",
        "Surface Chemistry",
        "Hydroxy Compounds and Ethers",
        "Carbonyl Compounds and Carboxylic Acids",
        "Organic Nitrogen Compounds",
        "Biomolecules",
        "Chemistry in Everyday Life"
    ],
    "Maths": [
        "Applications of Matrices and Determinants",
        "Complex Numbers",
        "Theory of Equations",
        "Inverse Trigonometric Functions",
        "Two Dimensional Analytical Geometry-II",
        "Applications of Vector Algebra",
        "Applications of Differential Calculus",
        "Differentials and Partial Derivatives",
        "Applications of Integration",
        "Ordinary Differential Equations",
        "Probability Distributions",
        "Discrete Mathematics"
    ]
}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/about", response_class=HTMLResponse)
async def read_about(request: Request):
    return templates.TemplateResponse(request=request, name="about.html")

@app.get("/confidential")
async def read_confidential():
    return RedirectResponse(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", status_code=status.HTTP_302_FOUND)

@app.get("/blessed-bees", response_class=HTMLResponse)
async def read_blessed_bees(request: Request):
    return templates.TemplateResponse(request=request, name="blessed_bees.html")

@app.get("/notes", response_class=HTMLResponse)
async def read_notes_hub(request: Request):
    return templates.TemplateResponse(request=request, name="notes_hub.html", context={
        "physics_count": len(TOPIC_MAP.get("Physics", [])),
        "chemistry_count": len(TOPIC_MAP.get("Chemistry", [])),
        "maths_count": len(TOPIC_MAP.get("Maths", [])),
    })

@app.get("/notes/{subject}", response_class=HTMLResponse)
async def read_notes(request: Request, subject: str, db: Session = Depends(get_db)):
    is_admin = check_is_admin(request)
    subject_title = subject.capitalize()
    notes = db.query(models.Note).filter(models.Note.subject.ilike(subject_title)).order_by(models.Note.upload_date.desc()).all()
    topics = TOPIC_MAP.get(subject_title, [])
    
    return templates.TemplateResponse(request=request, name="notes.html", context={
        "subject": subject_title, 
        "notes": notes,
        "topics": topics,
        "is_admin": is_admin
    })

@app.get("/upload", response_class=HTMLResponse)
async def read_upload(request: Request, username: str = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="upload.html")

@app.post("/api/upload-note")
async def upload_note(
    subject: str = Form(...),
    lesson_topic: str = Form(...),
    file_name: str = Form(...),
    drive_link: str = Form(...),
    db: Session = Depends(get_db),
    username: str = Depends(get_current_user)
):
    # Save to the database
    db_note = models.Note(
        subject=subject.capitalize(),
        lesson_topic=lesson_topic,
        file_name=file_name,
        file_path=drive_link
    )
    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    
    # Redirect back to the subject's page
    return RedirectResponse(url=f"/notes/{subject.capitalize()}", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/api/delete-note/{note_id}")
async def delete_note(
    request: Request,
    note_id: int, 
    db: Session = Depends(get_db)
):
    # Manually check admin status to provide a clear challenge if missing
    if not check_is_admin(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    note = db.query(models.Note).filter(models.Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
        
    subject = note.subject
    
    # Delete from filesystem safely (only for legacy local files)
    if not note.file_path.startswith("http") and os.path.exists(note.file_path):
        try:
            os.remove(note.file_path)
        except Exception:
            pass
            
    # Delete from DB
    db.delete(note)
    db.commit()
    
    return RedirectResponse(url=f"/notes/{subject}", status_code=status.HTTP_303_SEE_OTHER)
