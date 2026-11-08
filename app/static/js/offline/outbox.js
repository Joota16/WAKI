/* Compartido por la página y el service worker; no depende del DOM. */
(() => {
  const DATABASE = 'waki-report-outbox';
  let connection;
  function uuid() {
    if (crypto.randomUUID) return crypto.randomUUID();
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    const hex = [...bytes].map(byte => byte.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  function open() {
    if (!globalThis.indexedDB) return Promise.reject(Error('Este navegador no permite guardar reportes en el dispositivo.'));
    if (!connection) connection = new Promise((resolve, reject) => {
      const request = indexedDB.open(DATABASE, 1);
      request.onupgradeneeded = () => {
        request.result.createObjectStore('reports', { keyPath: 'id' });
        request.result.createObjectStore('photos');
      };
      request.onerror = () => reject(request.error);
      request.onblocked = () => reject(Error('Cierra las otras pestañas de WAKI y vuelve a intentar.'));
      request.onsuccess = () => {
        const db = request.result;
        db.onversionchange = () => { db.close(); connection = null; };
        resolve(db);
      };
    }).catch(error => { connection = null; throw error; });
    return connection;
  }

  async function transaction(mode, action) {
    const db = await open();
    return new Promise((resolve, reject) => {
      let tx;
      try { tx = db.transaction(['reports', 'photos'], mode, { durability: 'strict' }); }
      catch { tx = db.transaction(['reports', 'photos'], mode); }
      let result, failure;
      tx.oncomplete = () => resolve(result);
      tx.onabort = () => reject(failure || tx.error || Error('No se pudo guardar el reporte en el dispositivo.'));
      tx.onerror = () => { /* onabort entrega el error y evita confirmar una escritura fallida. */ };
      const set = value => { result = value; };
      const fail = error => { failure = error; tx.abort(); };
      try { action(tx.objectStore('reports'), tx.objectStore('photos'), set, fail); }
      catch (error) { fail(error); }
    });
  }

  const list = () => transaction('readonly', (reports, photos, set) => {
    reports.getAll().onsuccess = event => set(event.target.result.sort((a, b) => b.createdAt.localeCompare(a.createdAt)));
  });

  async function enqueue(metadata, files, timeoutMs, replaces = null) {
    const record = {
      id: uuid(), metadata, createdAt: metadata.client_created_at,
      state: 'pending', attempts: 0, nextAttemptAt: 0, leaseUntil: 0, leaseToken: null,
      timeoutMs, photoCount: files.length, message: '',
    };
    await transaction('readwrite', (reports, photos, set, fail) => {
      function save() {
        reports.add(record);
        photos.add(files.map(file => ({ blob: file, name: file.name, type: file.type })), record.id);
        set(record);
      }
      if (!replaces) return save();
      reports.get(replaces).onsuccess = event => {
        if (event.target.result?.state !== 'error') return fail(Error('El reporte cambió en otra pestaña. Actualiza los pendientes.'));
        reports.delete(replaces); photos.delete(replaces); save();
      };
    });
    return record;
  }

  function get(id) {
    return transaction('readonly', (reports, photos, set) => {
      reports.get(id).onsuccess = event => {
        const item = event.target.result;
        if (!item) return set(null);
        photos.get(id).onsuccess = event => set({ ...item, files: event.target.result || [] });
      };
    });
  }

  function claim(id, force = false) {
    return transaction('readwrite', (reports, photos, set) => {
      reports.get(id).onsuccess = event => {
        const item = event.target.result, now = Date.now();
        if (!item || !['pending', 'sending'].includes(item.state)
          || (item.state === 'sending' && item.leaseUntil > now)
          || (!force && item.nextAttemptAt > now)) return set(null);
        item.state = 'sending'; item.attempts += 1;
        item.leaseUntil = now + item.timeoutMs + 15000;
        item.leaseToken = uuid();
        reports.put(item);
        photos.get(id).onsuccess = event => set({ ...item, files: event.target.result || [] });
      };
    });
  }

  function finish(id, token, changes) {
    return transaction('readwrite', (reports, photos, set) => {
      reports.get(id).onsuccess = event => {
        const item = event.target.result;
        if (!item || item.leaseToken !== token) return set(false);
        Object.assign(item, changes, { leaseToken: null, leaseUntil: 0 });
        if (item.state === 'sent') {
          photos.delete(id);
          delete item.metadata; // El recibo local no conserva teléfono, coordenadas ni fotos.
        }
        reports.put(item); set(true);
        if (item.state === 'sent') reports.getAll().onsuccess = event => {
          const receipts = event.target.result.filter(row => row.state === 'sent')
            .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
          receipts.slice(20).forEach(row => reports.delete(row.id));
        };
      };
    });
  }

  function remove(id) {
    return transaction('readwrite', (reports, photos, set, fail) => {
      reports.get(id).onsuccess = event => {
        if (event.target.result?.state === 'sending' && event.target.result.leaseUntil > Date.now()) {
          return fail(Error('Espera a que termine el intento de envío.'));
        }
        reports.delete(id); photos.delete(id); set(true);
      };
    });
  }

  globalThis.WakiOutbox = { list, enqueue, get, claim, finish, remove };
})();
