// Servicio de conexión con la API FastAPI de QuantumGeoRescue
const ApiService = {
    hostActivo: null,

    // El backend responde errores en tres formatos distintos:
    //  - excepciones de dominio:  { error: true, codigo, mensaje }
    //  - HTTPException:           { detail: "texto" }
    //  - validación (422):        { detail: [ { loc, msg }, ... ] }
    extraerMensajeError(data, status) {
        if (data && typeof data === 'object') {
            if (typeof data.mensaje === 'string' && data.mensaje) return data.mensaje;
            if (typeof data.detail === 'string' && data.detail) return data.detail;
            if (Array.isArray(data.detail) && data.detail.length) {
                return data.detail.map((item) => {
                    const campo = Array.isArray(item.loc) ? item.loc.filter((parte) => parte !== 'body').join('.') : '';
                    return campo ? `${campo}: ${item.msg}` : String(item.msg || '');
                }).join(' | ');
            }
        }
        if (typeof data === 'string' && data) return data;
        return `Error en el servidor (HTTP ${status})`;
    },

    async abrirColaSOS() {
        if (!window.indexedDB) throw new Error("El almacenamiento local seguro no está disponible.");
        return new Promise((resolve, reject) => {
            const request = indexedDB.open("georescue-sos", 1);
            request.onupgradeneeded = () => {
                const db = request.result;
                if (!db.objectStoreNames.contains("alertas")) {
                    db.createObjectStore("alertas", { keyPath: "client_alert_id" });
                }
            };

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error || new Error("No se pudo abrir la cola SOS local."));
        });
    },

    async guardarAlertaSOS(payload, endpoint) {
        const db = await this.abrirColaSOS();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction("alertas", "readwrite");
            transaction.objectStore("alertas").put({
                ...payload,
                queue_endpoint: endpoint,
                queue_status: "PENDING",
                queue_attempts: 0,
                queue_next_attempt_at: 0,
                queue_last_error: null
            });
            transaction.oncomplete = () => { db.close(); resolve(); };
            transaction.onerror = () => { db.close(); reject(transaction.error || new Error("No se pudo guardar la alerta en la cola local.")); };
            transaction.onabort = () => { db.close(); reject(transaction.error || new Error("No se pudo confirmar la alerta en la cola local.")); };
        });
    },

    async actualizarAlertaSOS(payload) {
        const db = await this.abrirColaSOS();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction("alertas", "readwrite");
            transaction.objectStore("alertas").put(payload);
            transaction.oncomplete = () => { db.close(); resolve(); };
            transaction.onerror = () => { db.close(); reject(transaction.error || new Error("No se pudo actualizar la cola SOS local.")); };
        });
    },

    async listarAlertasSOS() {
        const db = await this.abrirColaSOS();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction("alertas", "readonly");
            const request = transaction.objectStore("alertas").getAll();
            request.onsuccess = () => { db.close(); resolve(request.result || []); };
            request.onerror = () => { db.close(); reject(request.error || new Error("No se pudo leer la cola SOS local.")); };
        });
    },

    async eliminarAlertaSOS(clientAlertId) {
        const db = await this.abrirColaSOS();
        return new Promise((resolve, reject) => {
            const transaction = db.transaction("alertas", "readwrite");
            transaction.objectStore("alertas").delete(clientAlertId);
            transaction.oncomplete = () => { db.close(); resolve(); };
            transaction.onerror = () => { db.close(); reject(transaction.error || new Error("No se pudo limpiar la cola SOS local.")); };
        });
    },

    async obtenerClientAlertId() {
        const cryptoApi = globalThis.crypto;
        if (cryptoApi && typeof cryptoApi.randomUUID === "function") return cryptoApi.randomUUID();
        if (!cryptoApi || typeof cryptoApi.getRandomValues !== "function") {
            throw new Error("No se pudo generar un identificador seguro para la alerta.");
        }
        const bytes = new Uint8Array(16);
        cryptoApi.getRandomValues(bytes);
        bytes[6] = (bytes[6] & 0x0f) | 0x40;
        bytes[8] = (bytes[8] & 0x3f) | 0x80;
        const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
        return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    },

    async despacharAlertaConCola(endpoint, payload) {
        await this.guardarAlertaSOS(payload, endpoint);
        try {
            const data = await this.request(endpoint, {
                method: "POST",
                body: JSON.stringify(payload)
            });
            await this.eliminarAlertaSOS(payload.client_alert_id);
            return data;
        } catch (error) {
            const pendientes = await this.listarAlertasSOS();
            const pendiente = pendientes.find((item) => item.client_alert_id === payload.client_alert_id);
            if (pendiente) {
                pendiente.queue_attempts += 1;
                pendiente.queue_next_attempt_at = Date.now() + Math.min(2000 * (2 ** (pendiente.queue_attempts - 1)), 3600000);
                pendiente.queue_status = error.status && error.status < 500 ? "REVIEW" : "PENDING";
                pendiente.queue_last_error = error.message;
                await this.actualizarAlertaSOS(pendiente);
            }
            error.alertaLocalGuardada = true;
            throw error;
        }
    },

    async reintentarAlertasSOS() {
        const pendientes = await this.listarAlertasSOS();
        for (const pendiente of pendientes) {
            if (pendiente.queue_status !== "PENDING" || pendiente.queue_next_attempt_at > Date.now()) continue;
            try {
                // Se reenvía exactamente lo que se intentó enviar la primera vez (incluidos
                // origen, confirmación y la marca de simulacro), sin los campos internos de la cola.
                const {
                    queue_endpoint, queue_status, queue_attempts, queue_next_attempt_at, queue_last_error,
                    ...payloadOriginal
                } = pendiente;
                await this.request(queue_endpoint, {
                    method: "POST",
                    body: JSON.stringify(payloadOriginal)
                });
                await this.eliminarAlertaSOS(pendiente.client_alert_id);
                window.dispatchEvent(new CustomEvent("georescue:sos-synced", {
                    detail: { client_alert_id: pendiente.client_alert_id }
                }));
            } catch (error) {
                pendiente.queue_attempts += 1;
                pendiente.queue_next_attempt_at = Date.now() + Math.min(2000 * (2 ** (pendiente.queue_attempts - 1)), 3600000);
                pendiente.queue_status = error.status && error.status < 500 ? "REVIEW" : "PENDING";
                pendiente.queue_last_error = error.message;
                await this.actualizarAlertaSOS(pendiente);
                if (!error.esRespuestaHttp || error.status >= 500) break;
            }
        }
    },

    async request(endpoint, options = {}) {
        let ultimoError = null;

        // Primero el host que ya respondió antes, para no reintentar puertos apagados en cada llamada.
        const hosts = this.hostActivo
            ? [this.hostActivo, ...CONFIG.API_HOSTS.filter((item) => item !== this.hostActivo)]
            : CONFIG.API_HOSTS;

        for (const host of hosts) {
            const urlConPrefijo = `${host}${CONFIG.API_PREFIX}${endpoint}`;
            const urlSinPrefijo = `${host}${endpoint}`;

            for (const url of [urlConPrefijo, urlSinPrefijo]) {
                try {
                    const response = await fetch(url, {
                        ...options,
                        headers: {
                            'Content-Type': 'application/json',
                            ...(localStorage.getItem(CONFIG.STORAGE_KEYS.TOKEN)
                                ? { Authorization: `Bearer ${localStorage.getItem(CONFIG.STORAGE_KEYS.TOKEN)}` }
                                : {}),
                            ...options.headers
                        }
                    });

                    let data = null;
                    try {
                        data = await response.json();
                    } catch (parseError) {
                        data = null;
                    }
                    if (!response.ok) {
                        const error = new Error(this.extraerMensajeError(data, response.status));
                        error.status = response.status;
                        error.esRespuestaHttp = true;
                        throw error;
                    }
                    this.hostActivo = host;
                    return data;
                } catch (err) {
                    ultimoError = err;
                    // Si el servidor respondió (aunque sea con 4xx/5xx) no es un error de red: se muestra tal cual.
                    if (err.esRespuestaHttp) {
                        throw err;
                    }
                }
            }
        }

        // Si fallaron todos los hosts (servidor apagado)
        const error = new Error("No se pudo conectar con el Backend (FastAPI).");
        error.esErrorRed = true;
        if (ultimoError) error.cause = ultimoError;
        throw error;
    },

    async verificarSalud() {
        for (const host of CONFIG.API_HOSTS) {
            try {
                const res = await fetch(`${host}/`);
                if (res.ok) {
                    this.hostActivo = host;
                    return await res.json();
                }
            } catch (e) {}
        }
        throw new Error("Servidor offline");
    },

    async registrarUsuario(payload) {
        return this.request('/auth/registro/', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    },

    async loginUsuario(payload) {
        return this.request('/auth/login/', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    },

    async verificarSesion() {
        return this.request('/auth/me/');
    },

    async aceptarInvitacionInstitucional(payload) {
        return this.request('/auth/invitaciones/aceptar/', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    },

    async registrarFamiliar(payload) {
        return this.request('/familia/agregar/', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    },

    async listarFamiliares(usuario) {
        return this.request(`/familia/listar/${encodeURIComponent(usuario)}`);
    },

    async listarInvitacionesFamiliares() {
        return this.request('/familia/invitaciones/recibidas/');
    },

    async listarInvitacionesEnviadas() {
        return this.request('/familia/invitaciones/enviadas/');
    },

    async responderInvitacionFamiliar(invitationId, aceptar) {
        const accion = aceptar ? 'aceptar' : 'rechazar';
        return this.request(`/familia/invitaciones/${invitationId}/${accion}/`, { method: 'POST' });
    },

    async revocarVinculoFamiliar(linkId) {
        return this.request(`/familia/vinculos/${linkId}/revocar/`, { method: 'POST' });
    },

    async listarBuzonFamiliar() {
        return this.request('/alertas/buzon-familiar/');
    },

    async despacharAlerta(payload) {
        return this.despacharAlertaConCola('/alertas/despachar/', payload);
    },

    async alertaCoaccion(payload) {
        return this.despacharAlertaConCola('/coaccion/alertar/', payload);
    },

    async obtenerAlertasActivas() {
        return this.request('/alertas/activas/');
    },

    async cambiarEstadoAlerta(alertaId, estado) {
        return this.request(`/alertas/${alertaId}/estado/`, {
            method: 'PATCH',
            body: JSON.stringify({ estado })
        });
    },

    async calcularRuta(payload) {
        return this.request('/rescate/calcular-ruta/', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    },

    async enviarAlertaSeguridad(payload) {
        return this.request('/security/anti-theft-alert', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    },

    async obtenerContactoSeguridad() {
        return this.request('/security/contact');
    },

    async guardarContactoSeguridad(correo) {
        return this.request('/security/contact', {
            method: 'PUT',
            body: JSON.stringify({ correo })
        });
    },

    async listarEvidenciasSeguridad() {
        return this.request('/security/events');
    },

    async obtenerFotoEvidencia(eventoId) {
        return this.request(`/security/events/${eventoId}/photo`);
    },

    async obtenerDirectorioEmergencia(version) {
        const consulta = version ? `?version=${encodeURIComponent(version)}` : '';
        return this.request(`/directorio/emergencia${consulta}`);
    },

    async listarPlanes() {
        return this.request('/subscriptions/plans');
    },

    async iniciarCheckoutPlan(payload) {
        return this.request('/subscriptions/checkout', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    },

    async confirmarCheckout(sessionId) {
        return this.request('/subscriptions/checkout/confirm', {
            method: 'POST',
            body: JSON.stringify({ session_id: sessionId })
        });
    },

    async obtenerMiPlan() {
        return this.request('/subscriptions/me');
    },

    async obtenerDatosDePago() {
        return this.request('/subscriptions/payment-info');
    },

    async agregarUsuarioInstitucional(payload) {
        return this.request('/subscriptions/institutions/members', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    },

    async listarUsuariosInstitucionales() {
        // La institución sale del token; así no depende de que el nombre viaje bien en la URL.
        return this.request('/subscriptions/institutions/me/members');
    },

    async obtenerCuentaInstitucional() {
        return this.request('/subscriptions/institutions/me');
    },

    async actualizarMiembroInstitucional(memberId, payload) {
        return this.request(`/subscriptions/institutions/me/members/${memberId}`, {
            method: 'PATCH',
            body: JSON.stringify(payload)
        });
    },

    async actualizarPlanInstitucional(planCode) {
        return this.request('/subscriptions/institutions/me/plan', {
            method: 'PUT',
            body: JSON.stringify({ plan_code: planCode })
        });
    },

    async loginPropietarios(accessKey) {
        return this.request('/admin/login', {
            method: 'POST',
            body: JSON.stringify({ access_key: accessKey })
        });
    },

    async cambiarContrasenaPropietarios(payload) {
        const token = sessionStorage.getItem('qgeo_owner_token');
        return this.request('/admin/change-password', {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` },
            body: JSON.stringify(payload)
        });
    },

    async listarSolicitudesInstitucionales(statusFilter = 'pending') {
        const token = sessionStorage.getItem('qgeo_owner_token');
        return this.request(`/admin/institution-applications?status_filter=${encodeURIComponent(statusFilter)}`, {
            headers: { Authorization: `Bearer ${token}` }
        });
    },

    async revisarSolicitudInstitucional(applicationId, action, payload) {
        const token = sessionStorage.getItem('qgeo_owner_token');
        return this.request(`/admin/institution-applications/${applicationId}/${action}`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` },
            body: JSON.stringify(payload)
        });
    },

    async listarPagosPorValidar() {
        const token = sessionStorage.getItem('qgeo_owner_token');
        return this.request('/admin/payments?status_filter=manual_review', {
            headers: { Authorization: `Bearer ${token}` }
        });
    },

    async revisarPago(paymentId, action) {
        const token = sessionStorage.getItem('qgeo_owner_token');
        return this.request(`/admin/payments/${paymentId}/${action}`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` }
        });
    },

    // Llamadas del panel de propietarios: usan su token, no el de la sesión de usuario.
    async requestPropietario(endpoint, options = {}) {
        const token = sessionStorage.getItem('qgeo_owner_token');
        return this.request(endpoint, {
            ...options,
            headers: { Authorization: `Bearer ${token}`, ...options.headers }
        });
    },

    async listarInstitucionesActivas() {
        return this.requestPropietario('/admin/institutions');
    },

    async validarCobertura(institutionId, payload) {
        return this.requestPropietario(`/admin/institutions/${institutionId}/coverage`, {
            method: 'PUT',
            body: JSON.stringify(payload)
        });
    },

    async retirarCobertura(institutionId) {
        return this.requestPropietario(`/admin/institutions/${institutionId}/coverage`, { method: 'DELETE' });
    },

    async listarAlertasSinAsignar() {
        return this.requestPropietario('/admin/alerts/unassigned');
    },

    async resumenDirectorio() {
        return this.requestPropietario('/admin/directory/summary');
    },

    async buscarDirectorio(texto) {
        return this.requestPropietario(`/admin/directory?limit=30&q=${encodeURIComponent(texto || '')}`);
    },

    async importarDirectorio(payload) {
        return this.requestPropietario('/admin/directory/import', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    },

    async corregirPuntoDirectorio(puntoId, payload) {
        return this.requestPropietario(`/admin/directory/${puntoId}`, {
            method: 'PATCH',
            body: JSON.stringify(payload)
        });
    },

    async asignarAlerta(alertaId, payload) {
        return this.requestPropietario(`/admin/alerts/${alertaId}/assign`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
    }
};

window.addEventListener("online", () => {
    ApiService.reintentarAlertasSOS().catch((error) => {
        console.error("No se pudo reintentar la cola SOS local:", error);
    });
});
