import os
from typing import List, Optional

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import create_document, get_documents, db

app = FastAPI(title="Recipe Genie API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


MEALDB_BASE = "https://www.themealdb.com/api/json/v1/1"


class FavoriteRecipeIn(BaseModel):
    meal_id: str
    title: str
    thumbnail: Optional[str] = None
    category: Optional[str] = None
    area: Optional[str] = None


@app.get("/")
def read_root():
    return {"message": "Recipe Genie backend is running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                response["collections"] = db.list_collection_names()[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    # env flags
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


@app.get("/api/recipes/search")
def search_recipes(q: str = Query(..., description="Search term, any language supported via MealDB search (English)")):
    # Themealdb search is English-based; we'll pass the term as-is
    try:
        r = requests.get(f"{MEALDB_BASE}/search.php", params={"s": q}, timeout=15)
        r.raise_for_status()
        data = r.json()
        meals = data.get("meals") or []
        return {"count": len(meals), "meals": meals}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Recipe search failed: {str(e)}")


@app.get("/api/recipes/random")
def random_recipe():
    try:
        r = requests.get(f"{MEALDB_BASE}/random.php", timeout=15)
        r.raise_for_status()
        data = r.json()
        return data
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Random recipe failed: {str(e)}")


@app.get("/api/recipes/{meal_id}")
def get_recipe(meal_id: str):
    try:
        r = requests.get(f"{MEALDB_BASE}/lookup.php", params={"i": meal_id}, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Recipe lookup failed: {str(e)}")


@app.post("/api/favorites")
def add_favorite(payload: FavoriteRecipeIn):
    try:
        doc_id = create_document("recipefavorite", payload.model_dump())
        return {"ok": True, "id": doc_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save favorite: {str(e)}")


@app.get("/api/favorites")
def list_favorites(limit: int = 50):
    try:
        docs = get_documents("recipefavorite", {}, limit)
        # convert ObjectId
        for d in docs:
            if "_id" in d:
                d["id"] = str(d.pop("_id"))
        return {"items": docs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list favorites: {str(e)}")


@app.get("/api/translate")
def translate_text(text: str, target: str = Query(..., description="Target language code, e.g., 'es', 'fr', 'hi', 'ar'")):
    """
    Translate text using LibreTranslate public instance (no key required).
    """
    try:
        resp = requests.post(
            "https://libretranslate.de/translate",
            timeout=20,
            headers={"Content-Type": "application/json"},
            json={"q": text, "source": "auto", "target": target, "format": "text"},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"Translation error: {resp.text[:120]}")
        out = resp.json()
        return {"translated": out.get("translatedText", "")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Translation service failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
