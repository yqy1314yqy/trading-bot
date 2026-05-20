from pythonforandroid.recipe import Recipe
from pythonforandroid.recipes.freetype import FreetypeRecipe as Base


class FreetypeRecipe(Base):
    url = "https://downloads.sourceforge.net/project/freetype/freetype2/{version}/freetype-{version}.tar.gz"
    version = "2.14.1"


recipe = FreetypeRecipe()
