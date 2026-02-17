import os
import json
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mistralai import Mistral
from pypdf import PdfReader  # Pure python, no binary issues

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Best practice: Fetch from environment variable only
api_key = os.getenv("MISTRAL_API_KEY","XuLqP7MaOAvMzfQTphhrh5HBnoCiz5KL")
client = Mistral(api_key=api_key)

def validate_financial_logic(data: dict):
    errors = []
    bs = data.get('balance_sheet', {})
    assets = bs.get('assets', {}).get('total_assets', 0)
    liabilities = bs.get('liabilities', {}).get('total_liabilities', 0)
    equity = bs.get('owners_equity', {}).get('total_shareholders_equity', 0)
    
    if assets != 0 and abs(assets - (liabilities + equity)) > 1:
        errors.append(f"Balance Sheet Mismatch: Assets ({assets}) != Liab+Equity ({liabilities + equity})")
    return errors

@app.get("/")
async def health():
    return {"message": "healthy and running"}

@app.post("/extract")
async def extract_financials(file: UploadFile = File(...)):
    # 1. Define path FIRST
    temp_path = f"/tmp/temp_{file.filename}"
    
    try:
        # 2. Save uploaded file
        content = await file.read()
        with open(temp_path, "wb") as buffer:
            buffer.write(content)

        # 3. Extract text using pypdf (Vercel-friendly)
        reader = PdfReader(temp_path)
        raw_text = ""
        for page in reader.pages:
            raw_text += page.extract_text() + "\n"

        if not raw_text.strip():
            raise ValueError("Could not extract text from PDF.")

        # 4. Multiplier Detection (Limit context to stay under timeout)
        unit_check = client.chat.complete(
            model="open-mistral-nemo",
            messages=[{
                "role": "user", 
                "content": f"Does this financial doc use 'millions' or 'billions'? Return ONLY the number (1000000, 1000000000, or 1). \n\n {raw_text[:3000]}"
            }]
        )
        
        try:
            multiplier = int(unit_check.choices[0].message.content.strip())
        except:
            multiplier = 1

        # 5. Data Extraction
        chat_completion = client.chat.complete(
            model="mistral-large-latest",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system", 
                    "content": f"Senior Auditor. Multiply numbers by {multiplier}. Return JSON."
                },
                {
                    "role": "user", 
                    "content": f"Extract financial data: \n\n {raw_text[:25000]}"
                }
            ]
        )

        data_json = json.loads(chat_completion.choices[0].message.content)
        
        # 6. Validation
        warnings = validate_financial_logic(data_json)
        if warnings:
            data_json["extraction_warnings"] = warnings

        return data_json

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)