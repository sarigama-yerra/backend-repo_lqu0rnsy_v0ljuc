import os
from typing import List, Optional

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import create_document, get_documents, db

app = FastAPI(title="Recipe Genie API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


MEALDB_BASE = "https://www.themealdb.com/api/json/v1/1"
LIBRE_TRANSLATE_URL = "https://libretranslate.de/translate"


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


def _translate_to_en(text: str) -> str:
    """Translate arbitrary text to English using LibreTranslate. Falls back to original on failure."""
    try:
        resp = requests.post(
            LIBRE_TRANSLATE_URL,
            timeout=20,
            headers={"Content-Type": "application/json"},
            json={"q": text, "source": "auto", "target": "en", "format": "text"},
        )
        if resp.status_code != 200:
            return text
        out = resp.json()
        translated = out.get("translatedText", "").strip()
        return translated or text
    except Exception:
        return text


def _mealdb_search_by_name(term: str):
    r = requests.get(f"{MEALDB_BASE}/search.php", params={"s": term}, timeout=15)
    r.raise_for_status()
    data = r.json()
    return data.get("meals") or []


def _mealdb_filter_by_ingredient(ingredient: str):
    """Filter by ingredient returns light-weight meal list; we enrich by lookup per id."""
    r = requests.get(f"{MEALDB_BASE}/filter.php", params={"i": ingredient}, timeout=15)
    r.raise_for_status()
    data = r.json()
    meals = data.get("meals") or []
    full_meals = []
    for m in meals[:12]:  # cap to avoid excessive calls
        mid = m.get("idMeal")
        if not mid:
            continue
        try:
            detail = requests.get(f"{MEALDB_BASE}/lookup.php", params={"i": mid}, timeout=15)
            detail.raise_for_status()
            dj = detail.json()
            if dj.get("meals"):
                full_meals.append(dj["meals"][0])
        except Exception:
            continue
    return full_meals


@app.get("/api/recipes/search")
def search_recipes(q: str = Query(..., description="Search in any language. We auto-translate and try ingredient fallback.")):
    try:
        # Try direct name search first
        meals = _mealdb_search_by_name(q)

        # If no results, translate to English and try again
        if not meals:
            q_en = _translate_to_en(q)
            if q_en and q_en.lower() != (q or "").lower():
                meals = _mealdb_search_by_name(q_en)

        # If still nothing, attempt ingredient filter (translate ingredient too)
        if not meals:
            ingredient = _translate_to_en(q)
            meals = _mealdb_filter_by_ingredient(ingredient)

        return {"count": len(meals), "meals": meals}
    except HTTPException:
        raise
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Recipe search failed: {str(e)}")
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
            LIBRE_TRANSLATE_URL,
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
