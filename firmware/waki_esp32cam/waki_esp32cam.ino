#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include "esp_camera.h"
#include "esp_system.h"
#include "secrets.h"
#include <WiFiClientSecure.h>
#include <time.h>
#include "tls_ca.h"

constexpr uint32_t INTERVALO_FOTO_MS = 60000;
constexpr uint32_t REINTENTO_WIFI_MS = 30000;
constexpr uint32_t REINTENTO_CAMARA_MS = 30000;
constexpr int FLASH_PIN = 4;

bool camaraLista = false;
bool wifiConectadoAntes = false;

uint32_t ultimaFoto = 0;
uint32_t ultimoReintentoWifi = 0;
uint32_t ultimoReintentoCamara = 0;
uint32_t fotosAceptadas = 0;
uint8_t fallosCaptura = 0;

bool iniciarCamara() {
  if (!psramFound()) {
    Serial.println(
      "WAKI: PSRAM no detectada. Revisar placa/configuracion."
    );
    return false;
  }

  camera_config_t config = {};

  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;

  config.pin_d0 = 5;
  config.pin_d1 = 18;
  config.pin_d2 = 19;
  config.pin_d3 = 21;
  config.pin_d4 = 36;
  config.pin_d5 = 39;
  config.pin_d6 = 34;
  config.pin_d7 = 35;

  config.pin_xclk = 0;
  config.pin_pclk = 22;
  config.pin_vsync = 25;
  config.pin_href = 23;
  config.pin_sccb_sda = 26;
  config.pin_sccb_scl = 27;
  config.pin_pwdn = 32;
  config.pin_reset = -1;

  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_XGA;
  config.jpeg_quality = 10;
  config.fb_count = 1;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;

  esp_err_t error = esp_camera_init(&config);

  if (error != ESP_OK) {
    Serial.printf(
      "WAKI: fallo al iniciar camara: 0x%x (%s).\n",
      static_cast<unsigned int>(error),
      esp_err_to_name(error)
    );
    return false;
  }

  sensor_t *sensor = esp_camera_sensor_get();

  if (sensor == nullptr) {
    Serial.println("WAKI: no se pudo obtener el sensor.");
    esp_camera_deinit();
    return false;
  }

  if (sensor->id.PID == OV3660_PID) {
    bool ajustesCorrectos = true;

    if (sensor->set_vflip(sensor, 1) != 0)
      ajustesCorrectos = false;
    if (sensor->set_brightness(sensor, 0) != 0)
      ajustesCorrectos = false;
    if (sensor->set_contrast(sensor, 1) != 0)
      ajustesCorrectos = false;
    if (sensor->set_saturation(sensor, 0) != 0)
      ajustesCorrectos = false;
    if (sensor->set_sharpness(sensor, 1) != 0)
      ajustesCorrectos = false;
    if (sensor->set_whitebal(sensor, 1) != 0)
      ajustesCorrectos = false;
    if (sensor->set_exposure_ctrl(sensor, 1) != 0)
      ajustesCorrectos = false;
    if (sensor->set_gain_ctrl(sensor, 1) != 0)
      ajustesCorrectos = false;

    if (!ajustesCorrectos) {
      Serial.println(
        "WAKI: fallo en ajustes del sensor; se reintentara."
      );
      esp_camera_deinit();
      return false;
    }
  }

  fallosCaptura = 0;
  Serial.printf(
    "WAKI: camara inicializada. Sensor PID: 0x%x.\n",
    static_cast<unsigned int>(sensor->id.PID)
  );
  Serial.println("WAKI: JPEG, XGA 1024x768, calidad 10.");
  return true;
}

void registrarFalloCaptura() {
  fallosCaptura++;

  Serial.printf(
    "WAKI: fallo de captura consecutivo %u/3.\n",
    static_cast<unsigned int>(fallosCaptura)
  );

  if (fallosCaptura >= 3) {
    esp_camera_deinit();
    camaraLista = false;
    ultimoReintentoCamara = millis();
    Serial.println("WAKI: camara detenida para reinicializar.");
  }
}

void enviarFotoAWaki() {
  if (!String(WAKI_URL).startsWith("https://")) {
    Serial.println("WAKI: configurar una URL HTTPS en secrets.h.");
    return;
  }

  if (time(nullptr) < 1735689600) {
    Serial.println("WAKI: esperando sincronizacion de hora.");
    return;
  }
  
  camera_fb_t *anterior = esp_camera_fb_get();

  if (anterior != nullptr) {
    esp_camera_fb_return(anterior);
  }

  camera_fb_t *foto = esp_camera_fb_get();

  if (foto == nullptr) {
    registrarFalloCaptura();
    return;
  }

  if (foto->format != PIXFORMAT_JPEG || foto->len == 0) {
    esp_camera_fb_return(foto);
    registrarFalloCaptura();
    return;
  }

  fallosCaptura = 0;

  WiFiClientSecure cliente;
  cliente.setCACert(WAKI_ROOT_CA);
  cliente.setHandshakeTimeout(15);
  HTTPClient http;

  http.setConnectTimeout(5000);
  http.setTimeout(15000);

  if (!http.begin(cliente, WAKI_URL)) {
    Serial.println("WAKI: no se pudo preparar la conexion HTTP.");
    esp_camera_fb_return(foto);
    return;
  }

  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-IoT-Key", WAKI_KEY);

  Serial.printf(
    "WAKI: enviando %ux%u, %u bytes, WiFi %d dBm...\n",
    static_cast<unsigned int>(foto->width),
    static_cast<unsigned int>(foto->height),
    static_cast<unsigned int>(foto->len),
    static_cast<int>(WiFi.RSSI())
  );

  uint32_t inicio = millis();
  int codigo = http.POST(foto->buf, foto->len);

  esp_camera_fb_return(foto);

  if (codigo == 201) {
    fotosAceptadas++;

    Serial.printf(
      "WAKI: foto aceptada. Total desde arranque: %lu. "
      "Tiempo: %lu ms.\n",
      static_cast<unsigned long>(fotosAceptadas),
      static_cast<unsigned long>(millis() - inicio)
    );
  } else if (codigo > 0) {
    Serial.printf("WAKI: respuesta HTTP %d.\n", codigo);
    Serial.println(http.getString());
  } else {
    Serial.printf(
      "WAKI: error de conexion: %s.\n",
      HTTPClient::errorToString(codigo).c_str()
    );
  }

  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(300);

  Serial.println("\nWAKI: iniciando dispositivo.");
  Serial.printf(
    "WAKI: motivo de reinicio: %d.\n",
    static_cast<int>(esp_reset_reason())
  );

  pinMode(FLASH_PIN, OUTPUT);
  digitalWrite(FLASH_PIN, LOW);

  if (strlen(WIFI_SSID) == 0 || strlen(WAKI_KEY) == 0) {
    Serial.println(
      "WAKI: completar WIFI_SSID y WAKI_KEY en secrets.h."
    );
    while (true) {
      delay(1000);
    }
  }

  camaraLista = iniciarCamara();
  ultimoReintentoCamara = millis();

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  WiFi.setSleep(false);

  ultimoReintentoWifi = millis();
  ultimaFoto = millis();

  Serial.println("WAKI: conectando al WiFi.");
  Serial.println("WAKI: intervalo de captura: 60 segundos.");
}

void loop() {
  uint32_t ahora = millis();

  if (!camaraLista &&
      ahora - ultimoReintentoCamara >= REINTENTO_CAMARA_MS) {
    Serial.println("WAKI: reintentando iniciar camara.");
    camaraLista = iniciarCamara();
    ultimoReintentoCamara = millis();
  }

  bool conectado = WiFi.status() == WL_CONNECTED;

  if (conectado && !wifiConectadoAntes) {
    configTime(0, 0, "time.google.com", "pool.ntp.org");
    Serial.println("WAKI: sincronizando hora para HTTPS.");
    Serial.print("WAKI: WiFi conectado. IP: ");
    Serial.println(WiFi.localIP());
  } else if (!conectado && wifiConectadoAntes) {
    Serial.println("WAKI: WiFi desconectado.");
  }

  wifiConectadoAntes = conectado;
  ahora = millis();

  if (!conectado &&
      ahora - ultimoReintentoWifi >= REINTENTO_WIFI_MS) {
    Serial.println("WAKI: reintentando WiFi.");
    WiFi.reconnect();
    ultimoReintentoWifi = millis();
  }

  if (conectado && camaraLista &&
      ahora - ultimaFoto >= INTERVALO_FOTO_MS) {
    ultimaFoto = ahora;
    enviarFotoAWaki();
  }

  delay(20);
}
