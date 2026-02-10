"""
AI Extraction Service - Claude Vision for PDF rate extraction.

Uses Anthropic's Claude to extract accommodation rates, room categories,
and seasons from supplier contract PDFs.
"""

import json
import base64
from typing import Optional, List
from datetime import datetime

from anthropic import Anthropic

from app.config import get_settings

settings = get_settings()


# ============================================================================
# Types for extraction results
# ============================================================================

class ExtractedRoomCategory:
    """Extracted room category from PDF."""
    def __init__(
        self,
        name: str,
        code: Optional[str] = None,
        max_occupancy: Optional[int] = None,
        max_adults: Optional[int] = None,
        max_children: Optional[int] = None,
        available_bed_types: Optional[List[str]] = None,
        description: Optional[str] = None,
    ):
        self.name = name
        self.code = code
        self.max_occupancy = max_occupancy or 2
        self.max_adults = max_adults or max_occupancy or 2
        self.max_children = max_children or 0
        self.available_bed_types = available_bed_types or ["DBL"]
        self.description = description

    def to_dict(self):
        return {
            "name": self.name,
            "code": self.code,
            "max_occupancy": self.max_occupancy,
            "max_adults": self.max_adults,
            "max_children": self.max_children,
            "available_bed_types": self.available_bed_types,
            "description": self.description,
        }


class ExtractedSeason:
    """Extracted season from PDF."""
    def __init__(
        self,
        name: str,
        code: Optional[str] = None,
        start_date: Optional[str] = None,  # MM-DD format
        end_date: Optional[str] = None,    # MM-DD format
        year=None,  # Can be int, string like "2024-2025", or None
        season_level: Optional[str] = None,  # low, high, peak
        original_name: Optional[str] = None,  # Original name from the contract
    ):
        self.name = name
        self.code = code
        self.start_date = start_date
        self.end_date = end_date
        # Convert year to string if provided
        self.year = str(year) if year is not None else None
        # Original name from the contract (before harmonization)
        self.original_name = original_name
        # Auto-detect season level from name if not provided
        self.season_level = season_level or self._detect_season_level(name)

    def _detect_season_level(self, name: str) -> str:
        """Auto-detect season level from season name."""
        name_lower = name.lower()

        # Peak seasons (Christmas, New Year, Easter, etc.)
        peak_keywords = ['noel', 'noël', 'christmas', 'new year', 'nouvel an',
                        'easter', 'pâques', 'paques', 'festive', 'peak', 'xmas',
                        'fête', 'fete', 'holiday']
        for keyword in peak_keywords:
            if keyword in name_lower:
                return 'peak'

        # Low seasons
        low_keywords = ['low', 'basse', 'green', 'mousson', 'monsoon', 'off-season',
                       'off season', 'shoulder', 'moyenne']
        for keyword in low_keywords:
            if keyword in name_lower:
                return 'low'

        # Default to high season
        return 'high'

    def to_dict(self):
        return {
            "name": self.name,
            "code": self.code,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "year": self.year,
            "season_level": self.season_level,
            "original_name": self.original_name,
        }


class ExtractedRate:
    """Extracted rate from PDF."""
    def __init__(
        self,
        room_code: str,
        season_code: Optional[str] = None,
        bed_type: str = "DBL",
        meal_plan: str = "BB",
        cost: float = 0,
        currency: str = "EUR",
        single_supplement: Optional[float] = None,
        extra_adult: Optional[float] = None,
        extra_child: Optional[float] = None,
    ):
        self.room_code = room_code
        self.season_code = season_code
        self.bed_type = bed_type
        self.meal_plan = meal_plan
        self.cost = cost
        self.currency = currency
        self.single_supplement = single_supplement
        self.extra_adult = extra_adult
        self.extra_child = extra_child

    def to_dict(self):
        return {
            "room_code": self.room_code,
            "season_code": self.season_code,
            "bed_type": self.bed_type,
            "meal_plan": self.meal_plan,
            "cost": self.cost,
            "currency": self.currency,
            "single_supplement": self.single_supplement,
            "extra_adult": self.extra_adult,
            "extra_child": self.extra_child,
        }


class ExtractedContractInfo:
    """Extracted contract metadata from PDF."""
    def __init__(
        self,
        name: Optional[str] = None,
        reference: Optional[str] = None,
        valid_from: Optional[str] = None,  # YYYY-MM-DD format
        valid_to: Optional[str] = None,    # YYYY-MM-DD format
        currency: Optional[str] = None,
    ):
        self.name = name
        self.reference = reference
        self.valid_from = valid_from
        self.valid_to = valid_to
        self.currency = currency

    def to_dict(self):
        return {
            "name": self.name,
            "reference": self.reference,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "currency": self.currency,
        }


class ExtractionResult:
    """Complete extraction result."""
    def __init__(
        self,
        room_categories: List[ExtractedRoomCategory],
        seasons: List[ExtractedSeason],
        rates: List[ExtractedRate],
        contract_info: Optional[ExtractedContractInfo] = None,
        source_file: Optional[str] = None,
        confidence_score: Optional[float] = None,
        warnings: Optional[List[str]] = None,
    ):
        self.room_categories = room_categories
        self.seasons = seasons
        self.rates = rates
        self.contract_info = contract_info
        self.source_file = source_file
        self.extracted_at = datetime.utcnow().isoformat()
        self.confidence_score = confidence_score
        self.warnings = warnings or []

    def to_dict(self):
        return {
            "room_categories": [c.to_dict() for c in self.room_categories],
            "seasons": [s.to_dict() for s in self.seasons],
            "rates": [r.to_dict() for r in self.rates],
            "contract_info": self.contract_info.to_dict() if self.contract_info else None,
            "source_file": self.source_file,
            "extracted_at": self.extracted_at,
            "confidence_score": self.confidence_score,
            "warnings": self.warnings,
        }


# ============================================================================
# Extraction prompt
# ============================================================================

EXTRACTION_PROMPT = """Tu es un assistant spécialisé dans l'extraction de données tarifaires depuis des contrats d'hébergement pour des tour-opérateurs (DMC).

Analyse ce document PDF de contrat hôtelier et extrais TOUTES les informations au format JSON strict.

## TRÈS IMPORTANT : Extraction des tarifs

Le document contient généralement un tableau avec :
- En lignes : les types de chambres (Standard, Superior, Suite, etc.)
- En colonnes : les saisons (Peak Season, Low Season, etc.)
- Dans les cellules : les prix en devise locale (THB, EUR, USD, etc.)

Tu DOIS créer une entrée dans "rates" pour CHAQUE combinaison chambre × saison visible dans le tableau.
Par exemple, si le PDF montre 7 types de chambres et 3 saisons, tu dois extraire 21 tarifs (7 × 3).

## HARMONISATION DES SAISONS (CRITIQUE - OBLIGATOIRE)

Chaque hôtel utilise sa propre nomenclature pour les saisons. Tu DOIS TOUJOURS HARMONISER vers ces noms FRANÇAIS standardisés :

### ATTENTION : Utilise TOUJOURS les noms français ci-dessous
- ❌ JAMAIS "High Season", "Low Season", "Peak Season"
- ✅ TOUJOURS "Haute Saison", "Basse Saison", "Fêtes"

### Codes de saison standardisés
| Code | Nom harmonisé (OBLIGATOIRE) | season_level | Appellations courantes à mapper |
|------|----------------------------|--------------|--------------------------------|
| HS   | Haute Saison               | high         | High Season, Peak Season, Hot Season, Dry Season, Winter, etc. |
| BS   | Basse Saison               | low          | Low Season, Green Season, Monsoon, Off Season, Shoulder, etc. |
| MS   | Moyenne Saison             | high         | Mid Season, Medium Season, Shoulder Season |
| PEAK | Fêtes                      | peak         | Christmas, New Year, Nouvel An, Noël, Easter, Pâques, CNY, Festive, etc. |

### Règles de mapping des saisons :
1. Identifie le SENS de chaque saison dans le document (haute/basse/fêtes)
2. Mappe vers le code standardisé correspondant (HS, BS, MS, PEAK)
3. Définis le season_level approprié (high, low, peak)
4. Conserve le nom ORIGINAL du document dans le champ "original_name"
5. Utilise le nom FRANÇAIS HARMONISÉ dans le champ "name" (Haute Saison, Basse Saison, Moyenne Saison, Fêtes)

### Exemples de mapping CORRECTS :
- "Green Season" → code: "BS", name: "Basse Saison", season_level: "low", original_name: "Green Season"
- "Peak Season" → code: "HS", name: "Haute Saison", season_level: "high", original_name: "Peak Season"
- "Festive Period" → code: "PEAK", name: "Fêtes", season_level: "peak", original_name: "Festive Period"
- "Winter High" → code: "HS", name: "Haute Saison", season_level: "high", original_name: "Winter High"
- "Low Season" → code: "BS", name: "Basse Saison", season_level: "low", original_name: "Low Season"
- "High Season" → code: "HS", name: "Haute Saison", season_level: "high", original_name: "High Season"

## Format de sortie attendu

```json
{
  "contract_info": {
    "name": "Contrat Tarifs 2024-2025",
    "reference": "REF-2024-001",
    "valid_from": "2024-11-01",
    "valid_to": "2025-10-31",
    "currency": "THB"
  },
  "room_categories": [
    {
      "name": "Standard Room",
      "code": "STD",
      "max_occupancy": 2,
      "max_adults": 2,
      "max_children": 1,
      "available_bed_types": ["DBL", "TWN"],
      "description": "Description si disponible"
    },
    {
      "name": "Deluxe Room",
      "code": "DLX",
      "max_occupancy": 2,
      "max_adults": 2,
      "max_children": 1,
      "available_bed_types": ["DBL"],
      "description": null
    }
  ],
  "seasons": [
    {
      "name": "Haute Saison",
      "code": "HS",
      "original_name": "Peak Season",
      "season_level": "high",
      "start_date": "11-01",
      "end_date": "04-30",
      "year": "2025-2026"
    },
    {
      "name": "Basse Saison",
      "code": "BS",
      "original_name": "Green Season",
      "season_level": "low",
      "start_date": "05-01",
      "end_date": "10-31",
      "year": "2026"
    },
    {
      "name": "Fêtes",
      "code": "PEAK",
      "original_name": "Christmas & New Year",
      "season_level": "peak",
      "start_date": "12-20",
      "end_date": "01-10",
      "year": "2025-2026"
    }
  ],
  "rates": [
    {
      "room_code": "STD",
      "season_code": "HS",
      "bed_type": "DBL",
      "meal_plan": "BB",
      "cost": 3500,
      "currency": "THB",
      "single_supplement": null,
      "extra_adult": null,
      "extra_child": null
    },
    {
      "room_code": "STD",
      "season_code": "BS",
      "bed_type": "DBL",
      "meal_plan": "BB",
      "cost": 2800,
      "currency": "THB",
      "single_supplement": null,
      "extra_adult": null,
      "extra_child": null
    },
    {
      "room_code": "DLX",
      "season_code": "PEAK",
      "bed_type": "DBL",
      "meal_plan": "BB",
      "cost": 5500,
      "currency": "THB",
      "single_supplement": null,
      "extra_adult": null,
      "extra_child": null
    }
  ],
  "warnings": ["Liste des avertissements si données incomplètes"]
}
```

## Règles d'extraction

### Types de lit (bed_type)
- SGL = Simple/Single
- DBL = Double (par défaut si non spécifié)
- TWN = Twin (lits jumeaux)
- TPL = Triple
- FAM = Familiale

### Plans repas (meal_plan)
- RO = Room Only (sans repas)
- BB = Bed & Breakfast (par défaut si non spécifié)
- HB = Half Board (demi-pension)
- FB = Full Board (pension complète)
- AI = All Inclusive (tout inclus)

### Dates - TRÈS IMPORTANT
- Format des dates: MM-DD (mois-jour), ex: "11-01" pour 1er Novembre
- TOUJOURS extraire l'année depuis le document et la mettre dans "year"
- Si les dates chevauchent 2 années (ex: 01/11/2025 au 30/04/2026), mettre year: "2025-2026"
- Si les dates sont dans la même année, mettre year: "2025"
- NE JAMAIS mettre year: null - les contrats ont TOUJOURS une période de validité annuelle
- Exemples :
  - "du 1er novembre 2025 au 30 avril 2026" → start_date: "11-01", end_date: "04-30", year: "2025-2026"
  - "du 1er mai 2026 au 31 octobre 2026" → start_date: "05-01", end_date: "10-31", year: "2026"

### Codes chambres
- Génère des codes courts (2-4 caractères) s'ils ne sont pas indiqués
- Utilise les premières lettres du nom en majuscules
- STD (Standard), SUP (Superior), DLX (Deluxe), STE (Suite), VIL (Villa), etc.

### Devises
- Détecte la devise du document (THB, EUR, USD, etc.)
- Utilise la même devise pour tous les tarifs

### Tarifs - CRITIQUE
- Extrais ABSOLUMENT TOUS les tarifs du tableau
- Un tarif = une cellule dans le tableau (intersection chambre/saison)
- room_code DOIT correspondre au code d'une room_category
- season_code DOIT correspondre au code HARMONISÉ d'une season (HS, BS, MS, PEAK)
- cost = le montant numérique (sans symbole de devise)

### Informations du contrat (contract_info)
- name: Titre du contrat ou nom de l'hôtel + "Tarifs" + année(s)
- reference: Numéro de référence du contrat si mentionné
- valid_from: Date de début de validité au format YYYY-MM-DD
- valid_to: Date de fin de validité au format YYYY-MM-DD
- currency: Devise principale des tarifs (THB, EUR, USD, etc.)

Si les dates de validité ne sont pas clairement indiquées, utilise les dates des saisons pour estimer (prends la date la plus ancienne comme valid_from et la plus récente comme valid_to).

## Important
- Retourne UNIQUEMENT le JSON, sans texte avant ou après
- Assure-toi que le JSON est valide
- Ne mets PAS de commentaires dans le JSON
- NE PAS oublier les tarifs - c'est la donnée la plus importante !
- HARMONISE les noms de saisons vers la nomenclature standard
"""


# ============================================================================
# AI Extraction Service
# ============================================================================

class AIExtractionService:
    """Service for extracting data from PDFs using Claude Vision."""

    def __init__(self):
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")
        self.client = Anthropic(api_key=settings.anthropic_api_key)

    async def extract_rates_from_pdf(
        self,
        pdf_content: bytes,
        filename: Optional[str] = None,
    ) -> ExtractionResult:
        """
        Extract room categories, seasons, and rates from a PDF contract.

        Args:
            pdf_content: Raw PDF bytes
            filename: Original filename for reference

        Returns:
            ExtractionResult with extracted data
        """
        # Encode PDF to base64
        pdf_base64 = base64.standard_b64encode(pdf_content).decode("utf-8")

        # Call Claude Vision
        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_base64,
                                },
                            },
                            {
                                "type": "text",
                                "text": EXTRACTION_PROMPT,
                            },
                        ],
                    }
                ],
            )
        except Exception as e:
            raise RuntimeError(f"Claude API error: {str(e)}")

        # Parse response
        response_text = message.content[0].text

        # Log raw response for debugging
        print(f"[AI EXTRACTION] Raw response length: {len(response_text)}")
        print(f"[AI EXTRACTION] Response preview: {response_text[:500]}...")

        # Extract JSON from response (in case there's extra text)
        try:
            # Try direct parse first
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to find JSON in response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                data = json.loads(json_match.group())
            else:
                raise ValueError("Could not parse JSON from Claude response")

        # Convert to typed objects
        room_categories = [
            ExtractedRoomCategory(**cat)
            for cat in data.get("room_categories", [])
        ]

        seasons = [
            ExtractedSeason(**season)
            for season in data.get("seasons", [])
        ]

        rates = [
            ExtractedRate(**rate)
            for rate in data.get("rates", [])
        ]

        # Extract contract info if available
        contract_info = None
        if data.get("contract_info"):
            contract_info = ExtractedContractInfo(**data["contract_info"])

        print(f"[AI EXTRACTION] Extracted: {len(room_categories)} categories, {len(seasons)} seasons, {len(rates)} rates")
        if contract_info:
            print(f"[AI EXTRACTION] Contract info: {contract_info.name}, valid {contract_info.valid_from} to {contract_info.valid_to}")

        warnings = data.get("warnings", [])

        # Calculate confidence score based on data completeness
        confidence = self._calculate_confidence(room_categories, seasons, rates)

        return ExtractionResult(
            room_categories=room_categories,
            seasons=seasons,
            rates=rates,
            contract_info=contract_info,
            source_file=filename,
            confidence_score=confidence,
            warnings=warnings,
        )

    def _calculate_confidence(
        self,
        categories: List[ExtractedRoomCategory],
        seasons: List[ExtractedSeason],
        rates: List[ExtractedRate],
    ) -> float:
        """Calculate confidence score based on extraction completeness."""
        score = 0.0

        # Has categories
        if categories:
            score += 0.25
            # All categories have names
            if all(c.name for c in categories):
                score += 0.1

        # Has seasons
        if seasons:
            score += 0.25
            # All seasons have dates
            if all(s.start_date and s.end_date for s in seasons):
                score += 0.1

        # Has rates
        if rates:
            score += 0.25
            # All rates have costs
            if all(r.cost > 0 for r in rates):
                score += 0.05

        # Rates reference valid categories and seasons
        cat_codes = {c.code or c.name for c in categories}
        season_codes = {s.code or s.name for s in seasons}
        season_codes.add(None)  # Default season

        valid_refs = all(
            r.room_code in cat_codes and (r.season_code is None or r.season_code in season_codes)
            for r in rates
        )
        if valid_refs:
            score += 0.1

        return min(score, 1.0)


# Singleton instance
_extraction_service: Optional[AIExtractionService] = None


def get_extraction_service() -> AIExtractionService:
    """Get or create the extraction service singleton."""
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = AIExtractionService()
    return _extraction_service
