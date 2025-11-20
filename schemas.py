from typing import Optional
from pydantic import BaseModel, Field

class RecipeFavorite(BaseModel):
    """
    Favorite recipes collection schema
    Collection name: recipefavorite
    """
    meal_id: str = Field(..., description="MealDB recipe idMeal")
    title: str = Field(..., description="Recipe title")
    thumbnail: Optional[str] = Field(None, description="Thumbnail image URL")
    category: Optional[str] = Field(None, description="Category")
    area: Optional[str] = Field(None, description="Cuisine area/country")
