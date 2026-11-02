import io
from urllib.parse import urljoin, urlparse

from PIL import Image, ImageChops, ImageDraw
import pytest

from test_pages import PageParser, client


def manifest_link(html):
    return next(attrs['href'] for tag, attrs in PageParser(html).elements
                if tag == 'link' and attrs.get('rel') == 'manifest')


@pytest.mark.parametrize('path', ['/', '/reportar', '/reportes', '/ingresar', '/registro'])
def test_installation_metadata_is_available_across_pages(client, path):
    response = client.get(path)
    assert response.status_code == 200
    page = PageParser(response.text)
    manifest = client.get(urljoin(path, manifest_link(response.text)))
    assert manifest.status_code == 200
    assert manifest.headers['content-type'].startswith('application/manifest+json')
    assert manifest.json()['start_url'] == '/'
    assert any(tag == 'meta' and attrs.get('name') == 'theme-color' for tag, attrs in page.elements)
    assert any(tag == 'meta' and attrs.get('name') == 'apple-mobile-web-app-capable'
               and attrs.get('content') == 'yes' for tag, attrs in page.elements)
    button = next(attrs for tag, attrs in page.elements if tag == 'button' and attrs.get('id') == 'pwa-install-button')
    assert button['type'] == 'button' and 'hidden' in button and button['aria-label'] == 'Instalar WAKI'
    assert any(tag == 'dialog' and attrs.get('id') == 'pwa-install-dialog' for tag, attrs in page.elements)


def test_manifest_and_real_icons_meet_installation_requirements(client):
    html = client.get('/').text
    manifest_url = manifest_link(html)
    manifest = client.get(manifest_url).json()
    assert manifest['name'] == 'WAKI' and manifest['short_name'] == 'WAKI'
    assert manifest['id'] == '/' and manifest['scope'] == '/'
    assert manifest['display'] == 'standalone'
    assert not manifest.get('prefer_related_applications', False)
    assert client.get(manifest['start_url']).status_code == 200
    install_sizes = set()
    for icon in manifest['icons']:
        assert not urlparse(icon['src']).netloc, 'Los iconos deben estar disponibles en el mismo servidor.'
        response = client.get(urljoin(manifest_url, icon['src']))
        assert response.status_code == 200 and response.headers['content-type'].startswith(icon['type'])
        with Image.open(io.BytesIO(response.content)) as image:
            size = tuple(int(value) for value in icon['sizes'].split('x'))
            assert image.format == 'PNG' and image.size == size
            assert image.convert('RGBA').getchannel('A').getextrema() == (255, 255)
            assert ImageChops.difference(image.convert('RGB'), Image.new('RGB', size, 'white')).getbbox()
        if 'any' in icon.get('purpose', 'any').split():
            install_sizes.add(size)
    assert {(192, 192), (512, 512)} <= install_sizes
    touch = next(attrs for tag, attrs in PageParser(html).elements
                 if tag == 'link' and attrs.get('rel') == 'apple-touch-icon')
    with Image.open(io.BytesIO(client.get(touch['href']).content)) as image:
        assert image.size == (180, 180) and image.format == 'PNG'


def test_maskable_logo_stays_inside_the_safe_zone(client):
    manifest_url = manifest_link(client.get('/').text)
    manifest = client.get(manifest_url).json()
    maskable = next(icon for icon in manifest['icons'] if 'maskable' in icon.get('purpose', '').split())
    with Image.open(io.BytesIO(client.get(urljoin(manifest_url, maskable['src'])).content)) as image:
        image = image.convert('RGB')
        width, height = image.size
        assert width == height
        logo = ImageChops.difference(image, Image.new('RGB', image.size, 'white')).convert('L')
        logo = logo.point(lambda value: 255 if value > 8 else 0)
        outside = Image.new('L', image.size, 255)
        ImageDraw.Draw(outside).ellipse((width * .1, height * .1, width * .9, height * .9), fill=0)
        assert ImageChops.multiply(logo, outside).getbbox() is None
