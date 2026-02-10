"""
Service Vertex AI pour la génération d'images avec Google Imagen.

Ce service utilise l'API Vertex AI de Google Cloud pour générer des images
à partir de descriptions textuelles (prompts).

Modèles disponibles (Imagen 3):
- imagen-3.0-generate-002 (Imagen 3) - Haute qualité, recommandé
- imagen-3.0-fast-generate-001 (Imagen 3 Fast) - Plus rapide, moins cher

Documentation:
https://cloud.google.com/vertex-ai/generative-ai/docs/image/generate-images
"""

import os
import base64
import logging
from typing import Optional, List
from pathlib import Path

import vertexai
from vertexai.preview.vision_models import ImageGenerationModel, GeneratedImage

logger = logging.getLogger(__name__)

# Configuration depuis les variables d'environnement
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "nomadays-creation")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

# Initialisation Vertex AI (une seule fois au démarrage)
_initialized = False


def _ensure_initialized():
    """Initialise Vertex AI si ce n'est pas déjà fait."""
    global _initialized
    if not _initialized:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        _initialized = True
        logger.info(f"Vertex AI initialisé: project={PROJECT_ID}, location={LOCATION}")


class ImageGenerationService:
    """Service de génération d'images avec Vertex AI Imagen."""

    # Modèles disponibles (Imagen 3)
    MODEL_IMAGEN_3 = "imagen-3.0-generate-002"  # Meilleure qualité
    MODEL_IMAGEN_3_FAST = "imagen-3.0-fast-generate-001"  # Plus rapide

    def __init__(self, model_name: str = MODEL_IMAGEN_3):
        """
        Initialise le service de génération d'images.

        Args:
            model_name: Nom du modèle Imagen à utiliser
        """
        _ensure_initialized()
        self.model_name = model_name
        self.model = ImageGenerationModel.from_pretrained(model_name)
        logger.info(f"ImageGenerationService initialisé avec le modèle: {model_name}")

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        number_of_images: int = 1,
        aspect_ratio: str = "1:1",
        guidance_scale: float = 7.5,
        seed: Optional[int] = None,
    ) -> List[GeneratedImage]:
        """
        Génère une ou plusieurs images à partir d'un prompt.

        Args:
            prompt: Description textuelle de l'image à générer
            negative_prompt: Ce qu'il faut éviter dans l'image
            number_of_images: Nombre d'images à générer (1-4)
            aspect_ratio: Ratio d'aspect ("1:1", "16:9", "9:16", "4:3", "3:4")
            guidance_scale: Force d'adhérence au prompt (1-30, défaut 7.5)
            seed: Graine pour reproductibilité (optionnel)

        Returns:
            Liste d'objets GeneratedImage

        Raises:
            Exception: En cas d'erreur de génération
        """
        try:
            logger.info(f"Génération d'image - Prompt: {prompt[:100]}...")

            # Paramètres de génération
            generation_params = {
                "prompt": prompt,
                "number_of_images": min(number_of_images, 4),  # Max 4
                "aspect_ratio": aspect_ratio,
                "guidance_scale": guidance_scale,
            }

            if negative_prompt:
                generation_params["negative_prompt"] = negative_prompt

            if seed is not None:
                generation_params["seed"] = seed

            # Génération
            images = self.model.generate_images(**generation_params)

            logger.info(f"Génération réussie: {len(images.images)} image(s)")
            return images.images

        except Exception as e:
            logger.error(f"Erreur de génération d'image: {str(e)}")
            raise

    async def generate_travel_image(
        self,
        destination: str,
        scene_type: str = "landscape",
        style: str = "photorealistic",
        time_of_day: str = "golden hour",
        number_of_images: int = 1,
    ) -> List[GeneratedImage]:
        """
        Génère une image de voyage optimisée pour le marketing.

        Args:
            destination: Nom de la destination (ex: "Chiang Mai, Thailand")
            scene_type: Type de scène ("landscape", "cityscape", "beach", "temple", "market", "nature")
            style: Style visuel ("photorealistic", "cinematic", "artistic", "dreamy")
            time_of_day: Moment de la journée ("sunrise", "golden hour", "sunset", "blue hour", "night")
            number_of_images: Nombre d'images à générer

        Returns:
            Liste d'images générées
        """
        # Construction du prompt optimisé pour le voyage
        style_descriptions = {
            "photorealistic": "ultra realistic, high resolution, DSLR photo quality",
            "cinematic": "cinematic lighting, movie scene, dramatic atmosphere",
            "artistic": "artistic interpretation, vibrant colors, creative composition",
            "dreamy": "soft focus, dreamy atmosphere, ethereal lighting",
        }

        scene_descriptions = {
            "landscape": "scenic landscape view, panoramic vista",
            "cityscape": "urban skyline, city architecture, bustling streets",
            "beach": "pristine beach, crystal clear water, tropical paradise",
            "temple": "ancient temple, sacred architecture, spiritual atmosphere",
            "market": "colorful local market, authentic culture, vibrant street life",
            "nature": "lush nature, tropical vegetation, natural beauty",
        }

        time_descriptions = {
            "sunrise": "early morning sunrise, soft pink and orange light",
            "golden hour": "golden hour lighting, warm tones, magical atmosphere",
            "sunset": "stunning sunset, dramatic sky colors",
            "blue hour": "blue hour twilight, serene atmosphere",
            "night": "nighttime scene, city lights, starry sky",
        }

        # Construction du prompt
        prompt = f"""Beautiful {scene_descriptions.get(scene_type, scene_type)} of {destination},
{time_descriptions.get(time_of_day, time_of_day)},
{style_descriptions.get(style, style)},
travel photography, inspiring wanderlust, magazine quality,
perfect for travel brochure, no people in foreground,
stunning composition, high dynamic range"""

        # Prompt négatif pour éviter les problèmes courants
        negative_prompt = """blurry, low quality, distorted, ugly,
watermark, text, logo, signature,
oversaturated, overexposed, underexposed,
unrealistic, artificial, fake looking,
tourists, crowds, modern vehicles"""

        return await self.generate_image(
            prompt=prompt,
            negative_prompt=negative_prompt,
            number_of_images=number_of_images,
            aspect_ratio="16:9",  # Format paysage pour le web
            guidance_scale=8.0,  # Adhérence forte au prompt
        )

    def save_image(
        self,
        image: GeneratedImage,
        output_path: str,
        format: str = "png"
    ) -> str:
        """
        Sauvegarde une image générée sur le disque.

        Args:
            image: Image générée par Vertex AI
            output_path: Chemin de sortie (sans extension)
            format: Format de sortie ("png", "jpeg")

        Returns:
            Chemin complet du fichier sauvegardé
        """
        full_path = f"{output_path}.{format}"
        image.save(full_path)
        logger.info(f"Image sauvegardée: {full_path}")
        return full_path

    def get_image_bytes(self, image: GeneratedImage) -> bytes:
        """
        Récupère les bytes d'une image générée.

        Args:
            image: Image générée par Vertex AI

        Returns:
            Bytes de l'image en PNG
        """
        return image._image_bytes

    def get_image_base64(self, image: GeneratedImage) -> str:
        """
        Récupère l'image en base64 pour affichage web.

        Args:
            image: Image générée par Vertex AI

        Returns:
            String base64 de l'image
        """
        return base64.b64encode(image._image_bytes).decode("utf-8")


# Instance singleton pour réutilisation
_service_instance: Optional[ImageGenerationService] = None


def get_image_generation_service() -> ImageGenerationService:
    """
    Récupère l'instance singleton du service de génération d'images.

    Returns:
        Instance de ImageGenerationService
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = ImageGenerationService()
    return _service_instance


# Fonction de test
async def test_generation():
    """Teste la génération d'une image."""
    service = get_image_generation_service()

    images = await service.generate_travel_image(
        destination="Chiang Mai, Thailand",
        scene_type="temple",
        style="cinematic",
        time_of_day="golden hour",
    )

    if images:
        # Sauvegarder la première image
        output_path = "/tmp/test_chiang_mai"
        saved_path = service.save_image(images[0], output_path)
        print(f"Image de test sauvegardée: {saved_path}")
        return saved_path

    return None


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_generation())
