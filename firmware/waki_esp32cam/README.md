# Firmware IoT de WAKI

Firmware para ESP32-CAM con pinout AI Thinker y cámara OV3660.
Captura fotografías JPEG y las envía al servidor WAKI.

## Hardware y herramientas

- ESP32-CAM AI Thinker con PSRAM y cámara OV3660.
- Base ESP32-CAM-MB con conexión USB.
- Cable USB de datos para programar.
- Arduino IDE con el paquete esp32 de Espressif.
- Red WiFi de 2,4 GHz.

Entorno utilizado: Arduino IDE 2.3.10 y paquete esp32 3.3.12.

## Configuración

1. Copiar secrets.example.h como secrets.h.
2. Completar WIFI_SSID, WIFI_PASSWORD, WAKI_URL y WAKI_KEY.
3. Usar en WAKI_KEY el mismo valor de IOT_KEY del servidor.
4. Mantener secrets.h fuera del control de versiones.

URL para pruebas locales:

http://IP_DE_LA_LAPTOP:8000/api/iot/upload?camera_id=chillon-01

La laptop y la ESP32 deben estar en la misma red y el servidor
debe ser accesible desde esa red.

## Compilación y carga

1. Abrir waki_esp32cam.ino en Arduino IDE.
2. Seleccionar la placa AI Thinker ESP32-CAM.
3. Seleccionar el puerto de la base USB.
4. Verificar y subir el programa.
5. Abrir el monitor serie a 115200 baudios.

Los pines están definidos dentro del archivo .ino.
No requiere board_config.h ni camera_pins.h.

## Funcionamiento

- Resolución XGA: 1024 × 768.
- Calidad JPEG: 10.
- Un buffer en PSRAM.
- Intervalo de envío: 60 segundos.
- Primer intento de envío aproximadamente un minuto después
  del arranque, si la cámara y el WiFi están disponibles.
- Flash apagado.
- Reintento de conexión WiFi cada 30 segundos.
- Reintento de inicialización de cámara cada 30 segundos.
- Reinicialización tras tres fallos consecutivos de captura.

La fotografía se envía como cuerpo binario mediante POST,
con Content-Type: image/jpeg y la cabecera X-IoT-Key.
El firmware considera aceptado el envío si recibe HTTP 201.

## Comprobación

- Confirmar envíos aceptados en el monitor serie.
- Comprobar una hora de recepción nueva en el dashboard.
- Consultar /api/cameras/chillon-01/latest para verificar
  dimensiones y metadatos de la última fotografía.
