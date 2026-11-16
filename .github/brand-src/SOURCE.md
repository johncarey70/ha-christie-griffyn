# Official Christie logo sources

The brand icons use the official Christie chevron mark published as the
site icon for [christiedigital.com](https://www.christiedigital.com/)
(favicon and apple-touch-icon), which is what browsers display in search
suggestions and on the home screen.

Primary source, 152×152 PNG, official apple-touch-icon:

https://www.christiedigital.com/apple-touch-icon.png

The same mark is used for the other published site icons on that domain,
including `/apple-touch-icon-152x152.png` and `/favicon-32x32.png`.

Christie also publishes a corporate wordmark pack at
[Christie logos](https://www.christiedigital.com/about/christie-logos/)
(`https://www.christiedigital.com/globalassets/about/logos/christie-logos.zip`,
March 2021). That pack is the horizontal CHRISTIE wordmark (EPS and
low-resolution JPG, black and blue), not the square chevron used as the
site icon. The site header SVG at
`https://www.christiedigital.com/contentassets/b41e8cfb4d724d46bc70f874bd320d5d/logo/christie.svg`
is that wordmark.

The official apple-touch-icon is stored here as base64 so it can be
committed as text. `.github/scripts/make_brand_icons.py` decodes it and
resizes to the Home Assistant brand sizes (256×256 `icon.png` and
512×512 `icon@2x.png`). `dark_icon` / `dark_icon@2x` use the same
official asset. The chevron's background is transparent in the source, so
the mark reads on both light and dark UI.

`logo.png` / `logo@2x.png` are omitted because the official site mark is
square; Home Assistant uses the icon as the logo fallback.

Christie and the Christie logo are trademarks of Christie Digital
Systems. This project is not affiliated with or endorsed by Christie.
