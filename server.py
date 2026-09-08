from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from scraper import scrape_reviews


app = FastAPI(
    title="Google Maps Review Agent",
    version="1.0.0"
)


# ============================================================
# REQUEST MODEL
# ============================================================

class ReviewRequest(BaseModel):
    url: str


# ============================================================
# HOME
# ============================================================

@app.get("/")
def home():
    return {
        "status": "success",
        "message": "Google Maps Review Agent is running"
    }


# ============================================================
# SCRAPE REVIEWS
# ============================================================

@app.post("/scrape-reviews")
def scrape_review_endpoint(request: ReviewRequest):

    try:

        print("\n======================================")
        print("Received Google Maps URL")
        print("======================================")
        print(request.url)

        result = scrape_reviews(request.url)

        return result

    except Exception as e:

        print("\nERROR:")
        print(str(e))

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )