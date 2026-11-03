from app.integrations.senamhi import STATIONS
from app.integrations.senamhi_discharge import DISCHARGE_STATIONS
from app.integrations.senamhi_weather import WEATHER_STATIONS
from app.repositories.discharge import discharge_row
from app.schemas.hydrology import DailyLevel, DischargeReading
from app.schemas.weather import DailyWeather


class MonitoringHistory:
    def __init__(self, database):
        self.database = database

    def get(self, river_id, metric, station_code, limit, offset):
        catalogs = {'level': list(STATIONS.values()), 'discharge': DISCHARGE_STATIONS,
                    'weather': list(WEATHER_STATIONS.values())}
        candidates = [station for station in catalogs[metric] if station.river_id == river_id
                      and (station_code is None or station.code == station_code)]
        if len(candidates) != 1:
            return None
        station = candidates[0]
        # Identificadores fijos: los parámetros del usuario no se interpolan en SQL.
        table, date_column, columns, model = {
            'level': ('hydrology_readings', 'observed_date', 'observed_date,level_m', DailyLevel),
            'discharge': ('discharge_readings', 'observed_at',
                          'observed_at,discharge_m3s,yellow_m3s,orange_m3s,red_m3s', DischargeReading),
            'weather': ('weather_readings', 'observed_date',
                        'observed_date,precipitation_mm,temperature_max_c,temperature_min_c', DailyWeather),
        }[metric]
        with self.database.connect() as db:
            db.execute('BEGIN')
            total = db.execute(f'SELECT COUNT(*) FROM {table} WHERE station_code=?', (station.code,)).fetchone()[0]
            rows = db.execute(f'SELECT {columns} FROM {table} WHERE station_code=? ORDER BY {date_column} DESC LIMIT ? OFFSET ?',
                              (station.code, limit, offset)).fetchall()
        return {'metric': metric, 'station': station.model_dump(mode='json'), 'total': total,
                'limit': limit, 'offset': offset,
                'items': [model(**(discharge_row(row) if metric == 'discharge' else dict(row))).model_dump(mode='json') for row in rows]}
