import os
import json
import shutil
import pymupdf4llm  # Optimized for LLM table extraction
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mistralai import Mistral

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Use environment variables for security
api_key = os.getenv("MISTRAL_API_KEY", "XuLqP7MaOAvMzfQTphhrh5HBnoCiz5KL")
client = Mistral(api_key=api_key)

def get_next_filename(base_name="extracted_output", extension="json"):
    counter = 1
    while os.path.exists(f"{base_name}_{counter}.{extension}"):
        counter += 1
    return f"{base_name}_{counter}.{extension}"

def validate_financial_logic(data: dict):
    """
    Performs basic accounting validation to catch common extraction errors.
    """
    errors = []
    
    # 1. Balance Sheet Equality: Assets = Liabilities + Equity
    assets = data.get('balance_sheet', {}).get('assets', {}).get('total_assets', 0)
    liabilities = data.get('balance_sheet', {}).get('liabilities', {}).get('total_liabilities', 0)
    equity = data.get('balance_sheet', {}).get('owners_equity', {}).get('total_shareholders_equity', 0)
    
    if assets != 0 and abs(assets - (liabilities + equity)) > 1:
        errors.append(f"Balance Sheet Mismatch: Assets ({assets}) != Liab+Equity ({liabilities + equity})")

    # 2. Retained Earnings Roll-forward: Opening + Net Income - Dividends = Closing
    re = data.get('retained_earnings', {})
    opening = re.get('opening_balance', 0)
    net_income = re.get('net_income', 0)
    dividends = re.get('dividends', 0)
    closing = re.get('closing_balance', 0)
    
    # Note: Dividends are often extracted as positive but should be subtracted
    if opening and closing and abs(opening + net_income - abs(dividends) - closing) > 1:
        # Check if there are 'Other' adjustments like stock repurchases affecting the balance
        errors.append("Retained earnings reconciliation check failed. Please verify repurchases or other equity adjustments.")

    return errors

@app.get("/")
async def health():
    return {"message": "healthy and running"}

@app.post("/extract")
async def extract_financials(file: UploadFile = File(...)):
    temp_path = f"temp_{file.filename}"
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        md_text = pymupdf4llm.to_markdown(temp_path)

        # STEP 2: UNIT MULTIPLIER DETECTION (Mistral Implementation)
        unit_check = client.chat.complete(
            model="open-mistral-nemo", # High speed, good for simple tasks
            messages=[{
                "role": "user", 
                "content": f"Look at the first few pages. Does it say 'In millions' or 'In billions'? Return ONLY the integer multiplier (1000000 or 1000000000). If not specified, return 1. \n\n {md_text[:5000]}"
            }]
        )
        
        try:
            multiplier = int(unit_check.choices[0].message.content.strip())
        except:
            multiplier = 1

        # STEP 3: PRECISION EXTRACTION (Using Mistral Large for accuracy)
        chat_completion = client.chat.complete(
            model="mistral-large-latest", # Best for complex JSON and reasoning
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system", 
                    "content": (
                        "You are a senior financial auditor. Your task is to extract data into a strict JSON format.\n"
                        f"1. Units: Reported in {multiplier}. Multiply all raw numbers by {multiplier}.\n"
                        "2. Negative Values: (500) -> -500.\n"
                        "3. Return ONLY valid JSON."
                    )
                },
                {
                    "role": "user", 
                    "content": f"Extract financial data: \n\n {md_text[:30000]}"
                }
            ]
        )

        data_json = json.loads(chat_completion.choices[0].message.content)

        # STEP 4: VERIFICATION & AUDIT
        # Add a field for validation warnings
        validation_errors = validate_financial_logic(data_json)
        if validation_errors:
            data_json["extraction_warnings"] = validation_errors

        # STEP 5: SAVE & RETURN
        output_filename = get_next_filename()
        with open(output_filename, "w") as f:
            json.dump(data_json, f, indent=4)

        return data_json

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)