"""
Genere une ombre portee "style Photoshop" pour une image RGBA (logo, texte...),
avec les parametres du panneau "Drop Shadow" de Photoshop : Color, Opacity,
Angle, Distance, Size.

Note : le parametre "Spread" a ete volontairement retire -- son implementation
via PIL ImageFilter.MaxFilter avec un grand noyau s'est averee bloquer le
serveur (plusieurs secondes, voire un timeout complet, meme avec un noyau
modeste sur une image de la taille d'un poster). Pas d'alternative rapide
trouvee avec les outils PIL disponibles.

Piege classique evite ici : appliquer un flou gaussien SANS agrandir le canvas
au prealable coupe le flou net aux bords de l'image d'origine. On agrandit
donc le canvas de travail avant le flou, pour laisser la place au degrade.
"""

import math
from PIL import Image, ImageFilter


def add_drop_shadow(
    source: Image.Image,
    opacity_pct: float = 60,
    angle_deg: float = -45,
    distance_px: float = 8,
    size_px: float = 15,
    shadow_color: tuple = (0, 0, 0),
) -> tuple:
    """
    Compose une ombre portee derriere `source`, avec les memes controles que
    Photoshop (sans Spread -- voir note en tete de module).

    Args:
        source: image RGBA source (logo/texte, silhouette definie par l'alpha)
        opacity_pct: opacite de l'ombre, 0-100
        angle_deg: angle de projection, -180 a +180 (0 = droite, 90 = haut,
                   convention Photoshop -- angle mathematique standard avec Y inverse)
        distance_px: distance de decalage, 0-100 (recommande)
        size_px: taille du flou (rayon gaussien), 0-250
        shadow_color: couleur RGB de l'ombre (tuple (r,g,b), 0-255 chacun)

    Returns:
        Tuple (image, padding) : l'image RGBA resultante (plus grande que
        `source`), et le padding (en pixels) ajoute de chaque cote -- a
        soustraire des coordonnees x,y prevues pour la source d'origine afin
        que le logo net reste exactement a sa position voulue sur le canvas
        final, avec l'ombre qui deborde tout autour.
    """
    if source.mode != "RGBA":
        source = source.convert("RGBA")

    opacity = max(0.0, min(1.0, opacity_pct / 100.0))
    blur_radius = max(0.0, size_px)

    # Angle + Distance -> offset x/y. Convention Photoshop : l'angle represente
    # la direction de la SOURCE DE LUMIERE, pas de l'ombre elle-meme -- l'ombre
    # tombe donc du cote OPPOSE (ex: angle=90 = lumiere d'en haut = ombre en bas).
    angle_rad = math.radians(angle_deg)
    offset_x = round(-distance_px * math.cos(angle_rad))
    offset_y = round(distance_px * math.sin(angle_rad))

    # Marge de securite : le flou + offset vont etaler les pixels au-dela
    # des bords d'origine.
    padding = int(blur_radius * 3) + max(abs(offset_x), abs(offset_y)) + 10

    padded_w = source.width + padding * 2
    padded_h = source.height + padding * 2

    # 1. Extrait la silhouette (canal alpha) sur fond transparent agrandi.
    alpha_mask = Image.new("L", (padded_w, padded_h), 0)
    alpha_mask.paste(source.split()[3], (padding, padding))

    # 2. Flou gaussien -- le degrade peut s'etaler librement dans la marge.
    if blur_radius > 0:
        blurred_alpha = alpha_mask.filter(ImageFilter.GaussianBlur(blur_radius))
    else:
        blurred_alpha = alpha_mask

    # 3. Couche d'ombre : couleur uniforme, opacite modulee par le masque.
    scaled_alpha = blurred_alpha.point(lambda p: int(p * opacity))
    solid_color_layer = Image.new("RGBA", (padded_w, padded_h), shadow_color + (0,))
    solid_color_layer.putalpha(scaled_alpha)
    shadow_layer = Image.new("RGBA", (padded_w, padded_h), (0, 0, 0, 0))
    shadow_layer = Image.alpha_composite(shadow_layer, solid_color_layer)

    # 4. Decale l'ombre selon l'angle/distance.
    shifted_shadow = Image.new("RGBA", (padded_w, padded_h), (0, 0, 0, 0))
    shifted_shadow.paste(shadow_layer, (offset_x, offset_y))

    # 5. Compose : ombre en dessous, source nette par-dessus.
    result = shifted_shadow.copy()
    source_positioned = Image.new("RGBA", (padded_w, padded_h), (0, 0, 0, 0))
    source_positioned.paste(source, (padding, padding), source)
    result = Image.alpha_composite(result, source_positioned)

    return result, padding