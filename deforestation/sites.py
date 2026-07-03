"""Registry of study areas for the multi-site, multi-biome evaluation.

Each site: bounding box (lon/lat), the Hansen GFC 10x10-degree tile that covers
it (for Global Forest Watch validation), and a short biome label. Boxes sit on
documented deforestation frontiers (confirmed on Global Forest Watch).
"""

# GFC tiles are named by their NW (top-left) corner in 10-degree steps.
GFC_BASE = ("/vsicurl/https://storage.googleapis.com/earthenginepartners-hansen/"
            "GFC-2024-v1.12/Hansen_GFC-2024-v1.12_lossyear_{tile}.tif")

SITES = {
    "rondonia": {
        "bbox": {"west": -63.10, "south": -10.00, "east": -62.85, "north": -9.78},
        "gfc_tile": "00N_070W", "biome": "Amazon (Brazil)",
    },
    "sao_felix_xingu": {
        "bbox": {"west": -52.10, "south": -6.70, "east": -51.85, "north": -6.48},
        "gfc_tile": "00N_060W", "biome": "Amazon (Brazil)",
    },
    "riau_sumatra": {
        "bbox": {"west": 101.40, "south": 0.30, "east": 101.65, "north": 0.55},
        "gfc_tile": "10N_100E", "biome": "Tropical peat / palm oil (Indonesia)",
    },
    "tshopo_drc": {
        "bbox": {"west": 24.90, "south": 0.30, "east": 25.15, "north": 0.55},
        "gfc_tile": "10N_020E", "biome": "Congo Basin rainforest (DRC)",
    },
    "santa_cruz_bolivia": {
        "bbox": {"west": -61.90, "south": -16.90, "east": -61.65, "north": -16.70},
        "gfc_tile": "10S_070W", "biome": "Chiquitano dry forest / soy (Bolivia)",
    },
}


def gfc_url(site_key: str) -> str:
    return GFC_BASE.format(tile=SITES[site_key]["gfc_tile"])
