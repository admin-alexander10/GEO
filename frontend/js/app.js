/**
 * QuantumGeoRescue AI - Lógica Principal del Frontend
 * Soporte B2C (Ciudadano & Familia) y B2G (Centro de Comando & Rescate)
 */

const App = {
    // Estado de la sesión y mapas
    usuarioActual: null,
    rolActual: null,
    institucionActual: null,
    socketInstitucional: null,
    _authFlowVersion: 0,
    _adminPanelHooked: false,
    mapaCiudadano: null,
    mapaB2G: null,
    marcadorCiudadano: null,
    marcadoresB2G: [],
    polilineaRutaB2G: null,
    marcadorBaseCOER: null,
    timerCuentaRegresiva: null,
    segundosRestantes: 10,
    reconocimientoVoz: null,
    escuchandoVoz: false,
    geolocalizacionActual: null,

    init() {
        this.verificarSaludBackend();
        this.verificarSesionPrevia();
        this.inicializarModuloAntirrobo();
        this.inicializarPlanesPago();
        this.cargarPreciosPlanes();
        this.inicializarAccesoInstitucional();
        this.inicializarAceptacionInvitacion();
        this.inicializarPanelAdministracion();
        this.inicializarValidacionDePagos();
        this.inicializarCoberturaYAsignacion();
        this.inicializarBandejaInstitucional();
        this.inicializarDirectorioPropietario();
        this.inicializarEvidenciaEnLlamadas();
        this.restaurarSesionPropietarios();
    },

    // El backend guarda las fechas en UTC sin indicar la zona. Se marcan como UTC
    // para que el navegador las muestre en la hora local del usuario.
    formatearFecha(valor) {
        if (!valor) return '—';
        const texto = String(valor);
        const iso = /(Z|[+-]\d{2}:\d{2})$/.test(texto) ? texto : `${texto}Z`;
        return new Date(iso).toLocaleString();
    },

    mostrarLoginPropietarios() {
        this.cerrarSesion();
        this.cambiarTabAuth('login');
        document.getElementById('form-login').classList.add('hidden');
        document.getElementById('form-registro').classList.add('hidden');
        document.getElementById('form-login-propietarios').classList.remove('hidden');
        document.getElementById('btn-acceso-propietarios').classList.add('hidden');
        document.getElementById('login-feedback').textContent = '';
    },

    ocultarLoginPropietarios() {
        document.getElementById('form-login-propietarios').classList.add('hidden');
        document.getElementById('btn-acceso-propietarios').classList.remove('hidden');
        this.cambiarTabAuth('login');
    },

    async manejarLoginPropietarios(event) {
        event.preventDefault();
        const keyInput = document.getElementById('clave-propietarios');
        const feedback = document.getElementById('owner-login-feedback');
        feedback.textContent = 'Validando acceso...';
        try {
            const response = await ApiService.loginPropietarios(keyInput.value);
            sessionStorage.setItem('qgeo_owner_token', response.access_token);
            sessionStorage.setItem('qgeo_owner_must_change_password', String(response.must_change_password));
            keyInput.value = '';
            this.mostrarPanelAdministracion();
            this.actualizarVistaCambioClavePropietario();
            if (!response.must_change_password) await this.cargarSolicitudesInstitucionales();
        } catch (error) {
            feedback.textContent = error.message;
            feedback.className = 'text-xs text-center min-h-[1rem] text-red-400';
        }
    },

    mostrarPanelAdministracion() {
        document.getElementById('pantalla-auth').classList.add('hidden');
        document.getElementById('pantalla-dashboard').classList.add('hidden');
        document.getElementById('panel-administracion').classList.remove('hidden');
    },

    restaurarSesionPropietarios() {
        if (sessionStorage.getItem('qgeo_owner_token')) {
            this.mostrarPanelAdministracion();
            this.actualizarVistaCambioClavePropietario();
            if (sessionStorage.getItem('qgeo_owner_must_change_password') !== 'true') {
                this.cargarSolicitudesInstitucionales();
            }
        }
    },

    actualizarVistaCambioClavePropietario() {
        const mustChange = sessionStorage.getItem('qgeo_owner_must_change_password') === 'true';
        document.getElementById('owner-password-change-form').classList.toggle('hidden', !mustChange);
        document.getElementById('owner-applications-section').classList.toggle('hidden', mustChange);
    },

    async cambiarContrasenaPropietarios(event) {
        event.preventDefault();
        const currentPassword = document.getElementById('owner-current-password').value;
        const newPassword = document.getElementById('owner-new-password').value;
        const confirmation = document.getElementById('owner-confirm-password').value;
        const feedback = document.getElementById('owner-password-feedback');
        if (newPassword !== confirmation) {
            feedback.textContent = 'Las contraseñas nuevas no coinciden.';
            feedback.className = 'mt-3 text-xs text-red-400';
            return;
        }
        feedback.textContent = 'Actualizando contraseña...';
        try {
            const response = await ApiService.cambiarContrasenaPropietarios({
                current_password: currentPassword,
                new_password: newPassword,
            });
            sessionStorage.setItem('qgeo_owner_token', response.access_token);
            sessionStorage.setItem('qgeo_owner_must_change_password', 'false');
            document.getElementById('owner-password-change-form').reset();
            this.actualizarVistaCambioClavePropietario();
            await this.cargarSolicitudesInstitucionales();
        } catch (error) {
            feedback.textContent = error.message;
            feedback.className = 'mt-3 text-xs text-red-400';
        }
    },

    cerrarSesionPropietarios() {
        sessionStorage.removeItem('qgeo_owner_token');
        sessionStorage.removeItem('qgeo_owner_must_change_password');
        document.getElementById('clave-propietarios').value = '';
        document.getElementById('owner-current-password').value = '';
        document.getElementById('owner-new-password').value = '';
        document.getElementById('owner-confirm-password').value = '';
        document.getElementById('panel-administracion').classList.add('hidden');
        document.getElementById('pantalla-auth').classList.remove('hidden');
        this.ocultarLoginPropietarios();
    },

    inicializarPanelAdministracion() {
        if (this._adminPanelHooked) return;
        this._adminPanelHooked = true;
        document.getElementById('owner-applications-list')?.addEventListener('click', async (event) => {
            const button = event.target.closest('[data-admin-action]');
            if (!button) return;
            const card = button.closest('[data-owner-application]');
            const applicationId = Number(card?.dataset.ownerApplication);
            const action = button.dataset.adminAction;
            const notes = card.querySelector('[data-review-notes]').value.trim();
            if (notes.length < 10) {
                alert('Escribe observaciones de revisión (mínimo 10 caracteres).');
                return;
            }

            let payload = { review_notes: notes };
            if (action === 'approve') {
                const source = card.querySelector('[data-verification-source]').value.trim();
                try {
                    if (new URL(source).protocol !== 'https:') throw new Error();
                } catch {
                    alert('Registra una URL HTTPS oficial que hayas consultado.');
                    return;
                }
                if (!window.confirm('¿Confirmas que contrastaste los datos en la fuente oficial y deseas aprobar esta institución?')) return;
                payload.verification_source = source;
            } else if (!window.confirm('¿Confirmas el rechazo? La institución y el solicitante permanecerán desactivados.')) {
                return;
            }

            button.disabled = true;
            try {
                await ApiService.revisarSolicitudInstitucional(applicationId, action === 'approve' ? 'approve' : 'reject', payload);
                await this.cargarSolicitudesInstitucionales();
            } catch (error) {
                button.disabled = false;
                alert(`No se pudo registrar la decisión: ${error.message}`);
            }
        });
    },

    inicializarValidacionDePagos() {
        if (this._ownerPaymentsHooked) return;
        this._ownerPaymentsHooked = true;
        document.getElementById('owner-payments-list')?.addEventListener('click', async (event) => {
            const button = event.target.closest('[data-payment-action]');
            if (!button) return;
            const paymentId = Number(button.closest('[data-owner-payment]')?.dataset.ownerPayment);
            const approve = button.dataset.paymentAction === 'approve';
            const pregunta = approve
                ? '¿Confirmas que el pago fue recibido? El plan se activará de inmediato.'
                : '¿Confirmas el rechazo? El usuario conservará su plan actual.';
            if (!window.confirm(pregunta)) return;
            button.disabled = true;
            try {
                await ApiService.revisarPago(paymentId, approve ? 'approve' : 'reject');
            } catch (error) {
                alert(`No se pudo registrar la decisión: ${error.message}`);
            }
            await this.cargarPagosPorValidar();
        });
    },

    async cargarSolicitudesInstitucionales() {
        const list = document.getElementById('owner-applications-list');
        const feedback = document.getElementById('owner-applications-feedback');
        if (!list || !sessionStorage.getItem('qgeo_owner_token') || sessionStorage.getItem('qgeo_owner_must_change_password') === 'true') return;
        const statusFilter = document.getElementById('owner-application-filter').value;
        feedback.textContent = 'Cargando solicitudes...';
        this.cargarPagosPorValidar();
        this.cargarCoberturas().then(() => this.cargarAlertasSinAsignar());
        this.cargarResumenDirectorio();
        try {
            const applications = await ApiService.listarSolicitudesInstitucionales(statusFilter);
            feedback.textContent = `${applications.length} solicitud(es)`;
            if (!applications.length) {
                list.innerHTML = '<p class="text-sm text-slate-400">No hay solicitudes para este filtro.</p>';
                return;
            }
            list.innerHTML = applications.map((application) => {
                const pending = application.status === 'pending';
                return `
                    <article data-owner-application="${application.id}" class="rounded-xl border border-slate-800 bg-slate-900 p-5">
                        <div class="flex items-start justify-between gap-3">
                            <div>
                                <h2 class="text-base font-bold text-white">${this.escaparTexto(application.institution_name)}</h2>
                                <p class="mt-1 text-xs text-slate-400">RUC ${this.escaparTexto(application.ruc)} · ${this.escaparTexto(application.institution_type)}</p>
                            </div>
                            <span class="rounded-md border border-slate-700 px-2 py-1 text-[10px] uppercase text-cyan-200">${this.escaparTexto(application.status)}</span>
                        </div>
                        <dl class="mt-4 grid grid-cols-1 gap-x-4 gap-y-2 text-xs sm:grid-cols-2">
                            <div><dt class="text-slate-500">Región</dt><dd class="text-slate-200">${this.escaparTexto(application.region)}</dd></div>
                            <div><dt class="text-slate-500">Solicitante</dt><dd class="text-slate-200">${this.escaparTexto(application.applicant_username)}</dd></div>
                            <div><dt class="text-slate-500">Contacto</dt><dd class="text-slate-200">${this.escaparTexto(application.contact_name)}</dd></div>
                            <div><dt class="text-slate-500">Teléfono</dt><dd class="text-slate-200">${this.escaparTexto(application.contact_phone)}</dd></div>
                            <div class="sm:col-span-2"><dt class="text-slate-500">Correo institucional</dt><dd class="text-slate-200">${this.escaparTexto(application.official_email)}</dd></div>
                            <div class="sm:col-span-2"><dt class="text-slate-500">Evidencia presentada</dt><dd><a class="break-all text-cyan-300 underline" href="${this.escaparTexto(application.evidence_url)}" target="_blank" rel="noopener noreferrer">Abrir enlace declarado</a></dd></div>
                            <div class="sm:col-span-2"><dt class="text-slate-500">Recibida</dt><dd class="text-slate-200">${this.escaparTexto(this.formatearFecha(application.submitted_at))}</dd></div>
                        </dl>
                        ${pending ? `
                            <div class="mt-4 space-y-3 border-t border-slate-800 pt-4">
                                <label class="block text-xs text-slate-300">Fuente oficial consultada (HTTPS)
                                    <input data-verification-source type="url" placeholder="https://www.gob.pe/..." class="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white" />
                                </label>
                                <label class="block text-xs text-slate-300">Observaciones de revisión
                                    <textarea data-review-notes minlength="10" rows="3" placeholder="Qué datos contrastaste y qué resultado obtuviste" class="mt-1 w-full resize-y rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white"></textarea>
                                </label>
                                <div class="flex justify-end gap-2">
                                    <button type="button" data-admin-action="reject" class="rounded-lg border border-red-800 px-3 py-2 text-xs text-red-300 hover:bg-red-950">Rechazar</button>
                                    <button type="button" data-admin-action="approve" class="rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-600">Aprobar institución</button>
                                </div>
                            </div>` : `
                            <div class="mt-4 border-t border-slate-800 pt-3 text-xs text-slate-400">
                                <p>Revisó: ${this.escaparTexto(application.reviewed_by || '—')}</p>
                                <p>Fuente: ${this.escaparTexto(application.verification_source || '—')}</p>
                                <p>Notas: ${this.escaparTexto(application.review_notes || '—')}</p>
                            </div>`}
                    </article>`;
            }).join('');
        } catch (error) {
            feedback.textContent = error.message;
            list.innerHTML = '';
            if (error.status === 401 || error.status === 403) this.cerrarSesionPropietarios();
        }
    },

    // ==========================================
    // PROPIETARIOS: COBERTURA Y ASIGNACIÓN DE ALERTAS
    // ==========================================
    inicializarCoberturaYAsignacion() {
        if (this._coberturaHooked) return;
        this._coberturaHooked = true;

        document.getElementById('owner-coverage-list')?.addEventListener('click', async (event) => {
            const button = event.target.closest('[data-coverage-action]');
            if (!button) return;
            const card = button.closest('[data-coverage-institution]');
            const institutionId = Number(card.dataset.coverageInstitution);
            try {
                if (button.dataset.coverageAction === 'remove') {
                    if (!window.confirm('¿Retirar la cobertura? La institución dejará de recibir alertas nuevas. Las que ya tiene se conservan.')) return;
                    button.disabled = true;
                    await ApiService.retirarCobertura(institutionId);
                } else {
                    const latitud = Number(card.querySelector('[data-coverage-lat]').value);
                    const longitud = Number(card.querySelector('[data-coverage-lng]').value);
                    const radio = Number(card.querySelector('[data-coverage-radius]').value);
                    const evidencia = card.querySelector('[data-coverage-evidence]').value.trim();
                    const vacio = ['[data-coverage-lat]', '[data-coverage-lng]', '[data-coverage-radius]']
                        .some((selector) => card.querySelector(selector).value.trim() === '');
                    if (vacio || !Number.isFinite(latitud) || !Number.isFinite(longitud) || latitud < -90 || latitud > 90 || longitud < -180 || longitud > 180) {
                        alert('Escribe la latitud y la longitud del centro en grados decimales, por ejemplo -7.1637 y -78.5003.');
                        return;
                    }
                    if (!(radio > 0 && radio <= 500)) {
                        alert('El radio debe estar entre 0 y 500 km.');
                        return;
                    }
                    if (evidencia.length < 10) {
                        alert('Anota qué documento o fuente respalda que la institución atiende esa zona (mínimo 10 caracteres).');
                        return;
                    }
                    if (!window.confirm(`¿Confirmas que esta institución atiende un radio de ${radio} km alrededor de ese punto? Empezará a recibir las alertas de esa zona.`)) return;
                    button.disabled = true;
                    await ApiService.validarCobertura(institutionId, { latitud, longitud, radio_km: radio, evidencia });
                }
                await this.cargarCoberturas();
                await this.cargarAlertasSinAsignar();
            } catch (error) {
                button.disabled = false;
                alert(`No se pudo guardar la cobertura: ${error.message}`);
            }
        });

        document.getElementById('owner-unassigned-list')?.addEventListener('click', async (event) => {
            const button = event.target.closest('[data-assign-alert]');
            if (!button) return;
            const card = button.closest('[data-unassigned-alert]');
            const alertaId = Number(card.dataset.unassignedAlert);
            const institucion = card.querySelector('[data-assign-institution]').value;
            const motivo = card.querySelector('[data-assign-reason]').value.trim();
            if (!institucion) {
                alert('Elige la institución que debe ver esta alerta.');
                return;
            }
            if (motivo.length < 10) {
                alert('Anota por qué le corresponde a esa institución (mínimo 10 caracteres).');
                return;
            }
            if (!window.confirm(`¿Asignar la alerta #${alertaId} a ${institucion}? Aparecerá en su bandeja.`)) return;
            button.disabled = true;
            try {
                await ApiService.asignarAlerta(alertaId, { institution_name: institucion, reason: motivo });
                await this.cargarAlertasSinAsignar();
            } catch (error) {
                button.disabled = false;
                alert(`No se pudo asignar la alerta: ${error.message}`);
            }
        });
    },

    async cargarCoberturas() {
        const list = document.getElementById('owner-coverage-list');
        const feedback = document.getElementById('owner-coverage-feedback');
        if (!list || !sessionStorage.getItem('qgeo_owner_token') || sessionStorage.getItem('qgeo_owner_must_change_password') === 'true') return;
        try {
            const instituciones = await ApiService.listarInstitucionesActivas();
            this._institucionesActivas = instituciones;
            const conCobertura = instituciones.filter((item) => item.coverage_validated_at).length;
            if (feedback) feedback.textContent = `${conCobertura} de ${instituciones.length} con cobertura validada`;
            if (!instituciones.length) {
                list.innerHTML = '<p class="text-sm text-slate-400">Aún no hay instituciones aprobadas.</p>';
                return;
            }
            const valor = (numero) => (numero === null || numero === undefined ? '' : this.escaparTexto(numero));
            list.innerHTML = instituciones.map((item) => {
                const validada = Boolean(item.coverage_validated_at);
                const mapa = validada
                    ? `https://www.openstreetmap.org/?mlat=${Number(item.coverage_lat)}&mlon=${Number(item.coverage_lng)}#map=11/${Number(item.coverage_lat)}/${Number(item.coverage_lng)}`
                    : '';
                return `
                <article data-coverage-institution="${Number(item.id)}" class="rounded-xl border border-slate-800 bg-slate-900 p-4 text-xs">
                    <div class="flex items-start justify-between gap-3">
                        <h3 class="text-sm font-bold text-white">${this.escaparTexto(item.institution_name)}</h3>
                        <span class="whitespace-nowrap rounded-md border px-2 py-1 text-[10px] uppercase ${validada ? 'border-emerald-700 text-emerald-200' : 'border-amber-700 text-amber-200'}">${validada ? 'Cobertura validada' : 'Sin cobertura'}</span>
                    </div>
                    <p class="mt-1 text-slate-400">${validada
                        ? `Validada por ${this.escaparTexto(item.coverage_validated_by || '—')} el ${this.escaparTexto(this.formatearFecha(item.coverage_validated_at))}. <a class="text-cyan-300 underline" href="${mapa}" target="_blank" rel="noopener noreferrer">Ver el centro en el mapa</a>`
                        : 'No recibe alertas automáticas hasta que valides su zona.'}</p>
                    <div class="mt-3 grid grid-cols-3 gap-2">
                        <label class="block text-slate-300">Latitud del centro
                            <input data-coverage-lat type="number" step="any" min="-90" max="90" value="${valor(item.coverage_lat)}" placeholder="-7.1637" class="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs text-white" />
                        </label>
                        <label class="block text-slate-300">Longitud del centro
                            <input data-coverage-lng type="number" step="any" min="-180" max="180" value="${valor(item.coverage_lng)}" placeholder="-78.5003" class="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs text-white" />
                        </label>
                        <label class="block text-slate-300">Radio (km)
                            <input data-coverage-radius type="number" step="any" min="0.1" max="500" value="${valor(item.coverage_radius_km)}" placeholder="15" class="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs text-white" />
                        </label>
                    </div>
                    <label class="mt-2 block text-slate-300">Evidencia de que atiende esa zona
                        <textarea data-coverage-evidence rows="2" minlength="10" placeholder="Documento, resolución o fuente oficial que consultaste" class="mt-1 w-full resize-y rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white">${this.escaparTexto(item.coverage_evidence || '')}</textarea>
                    </label>
                    <div class="mt-3 flex justify-end gap-2">
                        ${validada ? '<button type="button" data-coverage-action="remove" class="rounded-lg border border-red-800 px-3 py-2 text-xs text-red-300 hover:bg-red-950">Retirar cobertura</button>' : ''}
                        <button type="button" data-coverage-action="save" class="rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-600">${validada ? 'Actualizar cobertura' : 'Validar cobertura'}</button>
                    </div>
                </article>`;
            }).join('');
        } catch (error) {
            if (feedback) feedback.textContent = error.message;
            list.innerHTML = '';
        }
    },

    async cargarAlertasSinAsignar() {
        const list = document.getElementById('owner-unassigned-list');
        const feedback = document.getElementById('owner-unassigned-feedback');
        if (!list || !sessionStorage.getItem('qgeo_owner_token') || sessionStorage.getItem('qgeo_owner_must_change_password') === 'true') return;
        try {
            const alertas = await ApiService.listarAlertasSinAsignar();
            if (feedback) feedback.textContent = `${alertas.length} alerta(s) sin asignar`;
            if (!alertas.length) {
                list.innerHTML = '<p class="text-sm text-slate-400">Todas las alertas abiertas tienen una institución asignada.</p>';
                return;
            }
            const opciones = (this._institucionesActivas || [])
                .map((item) => `<option value="${this.escaparTexto(item.institution_name)}">${this.escaparTexto(item.institution_name)}</option>`)
                .join('');
            list.innerHTML = alertas.map((alerta) => {
                const tieneUbicacion = alerta.latitud !== null && alerta.longitud !== null;
                const ubicacion = tieneUbicacion
                    ? `${Number(alerta.latitud).toFixed(5)}, ${Number(alerta.longitud).toFixed(5)} · <a class="text-cyan-300 underline" href="https://www.openstreetmap.org/?mlat=${Number(alerta.latitud)}&mlon=${Number(alerta.longitud)}#map=14/${Number(alerta.latitud)}/${Number(alerta.longitud)}" target="_blank" rel="noopener noreferrer">ver en el mapa</a>`
                    : 'Sin ubicación';
                return `
                <article data-unassigned-alert="${Number(alerta.id)}" class="rounded-xl border border-amber-800/60 bg-slate-900 p-4 text-xs">
                    <div class="flex items-start justify-between gap-3">
                        <h3 class="text-sm font-bold text-white">#${Number(alerta.id)} · ${this.escaparTexto(alerta.tipo_emergencia)}</h3>
                        <span class="whitespace-nowrap rounded-md border border-slate-700 px-2 py-1 text-[10px] uppercase text-slate-200">Gravedad ${this.escaparTexto(alerta.nivel_gravedad ?? '—')}</span>
                    </div>
                    <p class="mt-1 text-slate-400">Usuario ${this.escaparTexto(alerta.usuario || '—')} · Canal ${this.escaparTexto(alerta.canal_entrada)} · ${this.escaparTexto(this.formatearFecha(alerta.creado_en))}</p>
                    <p class="mt-1 text-slate-300">${ubicacion}</p>
                    <p class="mt-1 text-slate-500">${tieneUbicacion ? 'Ninguna cobertura validada contiene este punto.' : 'El dispositivo no entregó ubicación.'}</p>
                    <label class="mt-3 block text-slate-300">Institución
                        <select data-assign-institution class="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-2 py-2 text-xs text-white">
                            <option value="">Elige una institución…</option>${opciones}
                        </select>
                    </label>
                    <label class="mt-2 block text-slate-300">Por qué le corresponde
                        <textarea data-assign-reason rows="2" minlength="10" placeholder="Cómo supiste a quién le toca atenderla" class="mt-1 w-full resize-y rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white"></textarea>
                    </label>
                    <div class="mt-3 flex justify-end">
                        <button type="button" data-assign-alert class="rounded-lg bg-cyan-700 px-3 py-2 text-xs font-semibold text-white hover:bg-cyan-600">Asignar a la institución</button>
                    </div>
                </article>`;
            }).join('');
        } catch (error) {
            if (feedback) feedback.textContent = error.message;
            list.innerHTML = '';
        }
    },

    // ==========================================
    // PROPIETARIOS: DIRECTORIO DE EMERGENCIA
    // ==========================================
    NOMBRES_TIPO_PUNTO: { COMISARIA: 'Comisaría', BOMBEROS: 'Bomberos', SALUD: 'Salud', SERENAZGO: 'Serenazgo', OTRO: 'Otro' },

    fechaLocalISO() {
        const hoy = new Date();
        return `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}-${String(hoy.getDate()).padStart(2, '0')}`;
    },

    inicializarDirectorioPropietario() {
        if (this._directorioHooked) return;
        this._directorioHooked = true;
        const fecha = document.getElementById('owner-directory-date');
        if (fecha) {
            fecha.value = this.fechaLocalISO();
            fecha.max = this.fechaLocalISO();
        }
        document.getElementById('owner-directory-list')?.addEventListener('click', async (event) => {
            const button = event.target.closest('[data-directory-action]');
            if (!button) return;
            const card = button.closest('[data-directory-point]');
            const puntoId = Number(card.dataset.directoryPoint);
            const accion = button.dataset.directoryAction;
            try {
                if (accion === 'edit') {
                    card.querySelector('[data-directory-form]').classList.toggle('hidden');
                    return;
                }
                if (accion === 'save') {
                    const telefono = card.querySelector('[data-directory-phone]').value.trim();
                    const fuente = card.querySelector('[data-directory-source]').value.trim();
                    if (fuente.length < 10) {
                        alert('Anota cómo comprobaste el número (mínimo 10 caracteres).');
                        return;
                    }
                    button.disabled = true;
                    await ApiService.corregirPuntoDirectorio(puntoId, { telefono: telefono || null, fuente, verificado_en: this.fechaLocalISO() });
                } else {
                    const activar = accion === 'activate';
                    if (!activar && !window.confirm('¿Ocultar esta entrada? Dejará de mostrarse en «Cerca de ti».')) return;
                    button.disabled = true;
                    await ApiService.corregirPuntoDirectorio(puntoId, { activo: activar });
                }
                await this.buscarEnDirectorio();
                await this.cargarResumenDirectorio();
            } catch (error) {
                button.disabled = false;
                alert(`No se pudo guardar el cambio: ${error.message}`);
            }
        });
    },

    async cargarResumenDirectorio() {
        const resumen = document.getElementById('owner-directory-summary');
        if (!resumen || !sessionStorage.getItem('qgeo_owner_token') || sessionStorage.getItem('qgeo_owner_must_change_password') === 'true') return;
        try {
            const datos = await ApiService.resumenDirectorio();
            const partes = Object.entries(datos.por_tipo || {})
                .map(([tipo, cantidad]) => `${this.NOMBRES_TIPO_PUNTO[tipo] || tipo}: ${cantidad}`);
            resumen.textContent = datos.total_activos
                ? `${datos.total_activos} entradas (${partes.join(', ')}) · ${datos.sin_telefono} sin teléfono`
                : 'Directorio vacío: la app solo muestra 105, 116 y 106.';
        } catch (error) {
            resumen.textContent = error.message;
        }
    },

    // Excel suele guardar CSV en Windows-1252; si al leerlo como UTF-8 hay caracteres
    // rotos se vuelve a leer con esa codificación para no perder tildes ni eñes.
    async leerArchivoCSV(archivo) {
        const bytes = await archivo.arrayBuffer();
        const utf8 = new TextDecoder('utf-8').decode(bytes);
        return utf8.includes('\uFFFD') ? new TextDecoder('windows-1252').decode(bytes) : utf8;
    },

    async importarDirectorio(event) {
        event.preventDefault();
        const resultado = document.getElementById('owner-directory-result');
        const archivo = document.getElementById('owner-directory-file').files[0];
        const boton = event.target.querySelector('button[type=submit]');
        if (!archivo) return;
        if (archivo.size > 2500000) {
            resultado.innerHTML = '<p class="text-red-400">El archivo pesa más de 2,5 MB. Divídelo en partes.</p>';
            return;
        }
        resultado.innerHTML = '<p class="text-slate-400">Cargando…</p>';
        boton.disabled = true;
        try {
            const csv = await this.leerArchivoCSV(archivo);
            const respuesta = await ApiService.importarDirectorio({
                csv,
                fuente: document.getElementById('owner-directory-source').value.trim(),
                verificado_en: document.getElementById('owner-directory-date').value,
                tipo_por_defecto: document.getElementById('owner-directory-type').value || null
            });
            const rechazos = respuesta.rechazados.map((fila) => `<li>Fila ${Number(fila.fila)}: ${this.escaparTexto(fila.motivo)}</li>`).join('');
            resultado.innerHTML = `
                <p class="text-emerald-400">${Number(respuesta.creados)} nuevas, ${Number(respuesta.actualizados)} actualizadas.</p>
                ${respuesta.sin_telefono ? `<p class="text-amber-300">${Number(respuesta.sin_telefono)} quedaron sin teléfono: se muestran con su dirección, sin botón de llamada.</p>` : ''}
                ${respuesta.con_ubicacion_aproximada ? `<p class="text-slate-300">${Number(respuesta.con_ubicacion_aproximada)} tienen ubicación aproximada: la app lo indica junto a la distancia.</p>` : ''}
                ${respuesta.total_rechazados ? `<p class="text-red-400">${Number(respuesta.total_rechazados)} filas no se cargaron${respuesta.total_rechazados > respuesta.rechazados.length ? ` (se listan las primeras ${respuesta.rechazados.length})` : ''}:</p><ul class="max-h-40 list-disc overflow-y-auto pl-5 text-slate-400">${rechazos}</ul>` : ''}
                <p class="text-slate-500">Columnas usadas: ${this.escaparTexto(respuesta.columnas_detectadas.join(' · '))}</p>`;
            await this.cargarResumenDirectorio();
            await this.buscarEnDirectorio();
        } catch (error) {
            resultado.innerHTML = `<p class="text-red-400">${this.escaparTexto(error.message)}</p>`;
        } finally {
            boton.disabled = false;
        }
    },

    async buscarEnDirectorio(event) {
        event?.preventDefault();
        const lista = document.getElementById('owner-directory-list');
        if (!lista) return;
        try {
            const puntos = await ApiService.buscarDirectorio(document.getElementById('owner-directory-search').value.trim());
            if (!puntos.length) {
                lista.innerHTML = '<p class="text-slate-400">Sin resultados.</p>';
                return;
            }
            lista.innerHTML = puntos.map((punto) => `
                <article data-directory-point="${Number(punto.id)}" class="rounded-lg border border-slate-800 bg-slate-950 p-3 ${punto.activo ? '' : 'opacity-60'}">
                    <div class="flex items-start justify-between gap-2">
                        <div class="min-w-0">
                            <div class="font-bold text-white">${this.escaparTexto(punto.nombre)}</div>
                            <div class="text-slate-400">${this.escaparTexto(this.NOMBRES_TIPO_PUNTO[punto.tipo] || punto.tipo)}${punto.distrito ? ` · ${this.escaparTexto(punto.distrito)}` : ''}${punto.activo ? '' : ' · oculta'}</div>
                            <div class="mt-1 text-slate-200">${punto.telefono ? this.escaparTexto(punto.telefono) : '<span class="text-amber-300">Sin teléfono</span>'}</div>
                            <div class="text-[10px] text-slate-500">${punto.ubicacion_aproximada ? 'Ubicación aproximada · ' : ''}Verificado el ${this.escaparTexto(punto.verificado_en)} · ${this.escaparTexto(punto.fuente)}</div>
                        </div>
                        <div class="flex flex-col items-end gap-1 whitespace-nowrap">
                            <button type="button" data-directory-action="edit" class="text-cyan-300 underline">Corregir teléfono</button>
                            <button type="button" data-directory-action="${punto.activo ? 'deactivate' : 'activate'}" class="text-slate-300 underline">${punto.activo ? 'Ocultar' : 'Volver a mostrar'}</button>
                        </div>
                    </div>
                    <div data-directory-form class="mt-2 hidden space-y-2 border-t border-slate-800 pt-2">
                        <input data-directory-phone type="tel" maxlength="40" value="${this.escaparTexto(punto.telefono || '')}" placeholder="Nuevo teléfono" aria-label="Nuevo teléfono" class="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white" />
                        <input data-directory-source type="text" maxlength="1000" placeholder="Cómo comprobaste el número (fuente)" aria-label="Fuente de la corrección" class="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white" />
                        <div class="flex justify-end"><button type="button" data-directory-action="save" class="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-600">Guardar teléfono</button></div>
                    </div>
                </article>`).join('');
        } catch (error) {
            lista.innerHTML = `<p class="text-red-400">${this.escaparTexto(error.message)}</p>`;
        }
    },

    inicializarAccesoInstitucional() {
        const boton = document.getElementById('btn-agregar-usuario-institucion');
        if (!boton || this._institucionalHooked) return;
        this._institucionalHooked = true;

        boton.addEventListener('click', async () => {
            const institutionName = this.institucionActual;
            const memberName = document.getElementById('institucion-usuario-nombre')?.value.trim();
            const memberEmail = document.getElementById('institucion-usuario-email')?.value.trim();
            const role = document.getElementById('institucion-rol')?.value || 'operador';

            if (!memberName || !memberEmail) {
                alert('Completa el nombre y el correo del usuario institucional.');
                return;
            }

            try {
                const respuesta = await ApiService.agregarUsuarioInstitucional({
                    institution_name: institutionName,
                    member_name: memberName,
                    member_email: memberEmail,
                    role,
                    total_users: 1,
                });

                const costoTotal = Number(respuesta.monthly_price || 0);
                document.getElementById('institucion-costo-mensual').textContent = `S/${costoTotal.toFixed(0)}`;
                const invitation = document.getElementById('institucion-enlace-invitacion');
                invitation.value = respuesta.invitation_url;
                invitation.classList.remove('hidden');
                alert(`Invitación creada para ${memberEmail}. Comparte el enlace antes de que expire en 48 horas.`);
                this.cargarUsuariosInstitucionales(institutionName);
                this.cargarCuentaInstitucional();
            } catch (error) {
                alert(`No se pudo agregar el usuario institucional: ${error.message}`);
            }
        });

        const contenedor = document.getElementById('miembros-institucion-b2g');
        contenedor?.addEventListener('click', async (event) => {
            const button = event.target.closest('[data-member-action]');
            if (!button) return;
            try {
                const memberCard = button.closest('[data-member-card]');
                const update = button.dataset.memberAction === 'save-role'
                    ? { role: memberCard.querySelector('.member-role').value }
                    : { is_active: button.dataset.memberAction === 'activate' };
                await ApiService.actualizarMiembroInstitucional(Number(button.dataset.memberId), {
                    ...update
                });
                await this.cargarUsuariosInstitucionales(this.institucionActual);
                await this.cargarCuentaInstitucional();
            } catch (error) {
                alert(`No se pudo actualizar el miembro: ${error.message}`);
            }
        });
    },

    async cargarUsuariosInstitucionales(institutionName) {
        const contenedor = document.getElementById('miembros-institucion-b2g');
        if (!contenedor) return;

        try {
            const miembros = await ApiService.listarUsuariosInstitucionales();
            const contador = document.getElementById('contador-miembros-institucion');
            const activos = miembros.filter((miembro) => miembro.is_active);
            if (contador) contador.textContent = String(activos.length);

            if (!miembros || miembros.length === 0) {
                contenedor.innerHTML = '<p class="text-xs text-slate-500">Aún no hay miembros en esta cuenta.</p>';
                return;
            }

            contenedor.innerHTML = miembros.map((miembro) => `
                <div data-member-card class="bg-emerald-950/40 border border-emerald-800 rounded-xl p-2 text-xs text-emerald-200">
                    <div class="flex items-center justify-between gap-2">
                        <span class="font-bold">${this.escaparTexto(miembro.member_name)}</span>
                        <span class="text-[10px] bg-emerald-900/70 text-emerald-200 px-1.5 py-0.5 rounded-full">${this.escaparTexto(miembro.role)}</span>
                    </div>
                    <div class="text-[10px] text-emerald-300/80 mt-1">${this.escaparTexto(miembro.member_email)}</div>
                    <div class="flex items-center justify-between mt-2">
                        <span class="text-[10px] ${miembro.is_active ? 'text-emerald-300' : 'text-slate-400'}">${miembro.is_active ? 'Activo' : 'Desactivado'}</span>
                        <button type="button" data-member-id="${miembro.id}" data-member-action="${miembro.is_active ? 'deactivate' : 'activate'}" class="text-[10px] underline text-slate-200">${miembro.is_active ? 'Desactivar' : 'Reactivar'}</button>
                    </div>
                    <div class="flex gap-1 mt-2">
                        <select class="member-role flex-1 bg-slate-900 border border-slate-700 rounded px-1 py-1 text-[10px]" aria-label="Rol de ${this.escaparTexto(miembro.member_name)}">
                            ${['operador', 'analista', 'coordinador'].map((role) => `<option value="${role}" ${miembro.role === role ? 'selected' : ''}>${role}</option>`).join('')}
                        </select>
                        <button type="button" data-member-id="${miembro.id}" data-member-action="save-role" class="text-[10px] underline text-slate-200">Guardar rol</button>
                    </div>
                </div>
            `).join('');
        } catch (error) {
            contenedor.innerHTML = `<p class="text-xs text-red-400">No se pudo cargar la lista institucional: ${error.message}</p>`;
        }
    },

    escaparTexto(value) {
        const element = document.createElement('span');
        element.textContent = String(value ?? '');
        return element.innerHTML;
    },

    inicializarAceptacionInvitacion() {
        const params = new URLSearchParams(window.location.search);
        const invitationToken = params.get('invite');
        const form = document.getElementById('form-aceptar-invitacion');
        if (!invitationToken || !form) return;
        form.classList.remove('hidden');
        document.getElementById('form-login')?.classList.add('hidden');
        document.getElementById('form-registro')?.classList.add('hidden');
        document.querySelector('.grid.grid-cols-2.bg-slate-950')?.classList.add('hidden');
        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            const feedback = document.getElementById('invitacion-feedback');
            const password = document.getElementById('invitacion-password').value;
            feedback.textContent = 'Validando invitación...';
            try {
                const data = await ApiService.aceptarInvitacionInstitucional({ token: invitationToken, password });
                this.guardarSesion(data);
                params.delete('invite');
                history.replaceState({}, '', `${location.pathname}${params.size ? `?${params}` : ''}`);
                this.iniciarSesionEnUI(data.usuario, data.rol, data.codigo_enlace, data.institucion);
            } catch (error) {
                feedback.textContent = error.message;
                feedback.className = 'text-xs text-center min-h-[1rem] text-red-400';
            }
        });
    },

    guardarSesion(data) {
        localStorage.setItem(CONFIG.STORAGE_KEYS.USER, data.usuario);
        localStorage.setItem(CONFIG.STORAGE_KEYS.ROLE, data.rol);
        localStorage.setItem(CONFIG.STORAGE_KEYS.TOKEN, data.token);
        localStorage.setItem(CONFIG.STORAGE_KEYS.INSTITUTION, data.institucion || 'individual');
        if (data.codigo_enlace) localStorage.setItem(CONFIG.STORAGE_KEYS.CODE, data.codigo_enlace);
    },

    async cargarCuentaInstitucional() {
        if (!this.institucionActual) return;
        try {
            const account = await ApiService.obtenerCuentaInstitucional();
            const nombre = document.getElementById('institucion-nombre');
            if (nombre) nombre.value = account.institution_name;
            const included = document.getElementById('institucion-usuarios-incluidos');
            const extra = document.getElementById('institucion-usuarios-extra');
            const price = document.getElementById('institucion-costo-mensual');
            if (included) included.textContent = String(account.included_users);
            if (extra) extra.textContent = String(account.extra_users);
            if (price) price.textContent = `${account.currency} ${Number(account.monthly_total).toFixed(2)}`;
            const plan = document.getElementById('institucion-plan');
            if (plan) plan.value = account.plan_code;
        } catch (error) {
            console.warn('No se pudo cargar la cuenta institucional:', error.message);
        }
    },

    async guardarPlanInstitucional() {
        const planCode = document.getElementById('institucion-plan')?.value;
        if (!planCode) return;
        try {
            await ApiService.actualizarPlanInstitucional(planCode);
            await this.cargarCuentaInstitucional();
            alert('Plan institucional actualizado.');
        } catch (error) {
            alert(`No se pudo actualizar el plan: ${error.message}`);
        }
    },

    conectarTiempoRealInstitucional() {
        this.socketInstitucional?.close();
        const token = localStorage.getItem(CONFIG.STORAGE_KEYS.TOKEN);
        if (!token || !this.institucionActual || this.rolActual === 'ciudadano') return;
        const apiHost = (ApiService.hostActivo || CONFIG.API_HOSTS[0]).replace(/^http/, 'ws');
        const socket = new WebSocket(`${apiHost}${CONFIG.API_PREFIX}/realtime/ws/alerts`);
        this.socketInstitucional = socket;
        socket.addEventListener('open', () => socket.send(JSON.stringify({ token })));
        socket.addEventListener('message', (event) => {
            try {
                const notification = JSON.parse(event.data);
                if (['alert.created', 'alert.updated'].includes(notification.type)) this.cargarAlertasB2G();
            } catch (error) {
                console.warn('Evento de tiempo real inválido.', error);
            }
        });
        socket.addEventListener('close', () => {
            if (this.socketInstitucional === socket && this.usuarioActual) {
                window.setTimeout(() => this.conectarTiempoRealInstitucional(), 4000);
            }
        });
    },

    // ==========================================
    // PLANES Y PAGOS
    // ==========================================
    NOMBRES_PLAN: { free: 'Free', pro: 'Pro', enterprise: 'Enterprise' },
    NOMBRES_METODO_PAGO: { yape: 'Yape', plin: 'Plin', transferencia: 'Transferencia bancaria' },

    mostrarMensajePlanes(mensaje) {
        const feedback = document.getElementById('planes-feedback');
        if (feedback) feedback.textContent = mensaje;
    },

    inicializarPlanesPago() {
        document.querySelectorAll('.plan-select').forEach((button) => {
            button.addEventListener('click', () => {
                const planCode = button.dataset.plan;

                if (planCode === 'enterprise') {
                    // Enterprise es el plan de las instituciones: se solicita con el registro institucional.
                    this.cambiarTabAuth('registro');
                    this.cambiarModoRegistro('institucional');
                    this.mostrarMensajePlanes('El plan Enterprise es para instituciones públicas: completa el registro como "Institución pública".');
                    return;
                }

                if (this.usuarioActual) {
                    this.contratarPlan(planCode);
                    return;
                }

                if (planCode === 'free') {
                    this.cambiarTabAuth('registro');
                    this.cambiarModoRegistro('familiar');
                    this.mostrarMensajePlanes('El plan Free ya viene incluido: solo crea tu cuenta en el acceso Familiar.');
                    return;
                }

                // Sin sesión no se registra ningún pago: se recuerda el plan y se contrata al iniciar sesión.
                sessionStorage.setItem('qgeo_pending_plan', planCode);
                this.mostrarMensajePlanes(`Inicia sesión o regístrate en el acceso Familiar para activar el plan ${this.NOMBRES_PLAN[planCode] || planCode}.`);
            });
        });
    },

    // Los precios se leen del backend para que la tarjeta, el formulario de pago y el
    // panel del propietario muestren siempre el mismo monto.
    async cargarPreciosPlanes() {
        try {
            const planes = await ApiService.listarPlanes();
            this.planes = Object.fromEntries(planes.map((plan) => [plan.code, plan]));
            document.querySelectorAll('[data-plan-price]').forEach((etiqueta) => {
                const plan = this.planes[etiqueta.dataset.planPrice];
                if (plan) etiqueta.textContent = `S/${Number(plan.price).toFixed(0)}`;
            });
        } catch (err) {
            console.warn('No se pudo cargar el catálogo de planes:', err.message);
        }
    },

    async contratarPlan(planCode) {
        if (planCode === 'free') {
            await this.enviarCheckout({ plan_code: planCode });
            return;
        }
        let datosDePago;
        try {
            datosDePago = await ApiService.obtenerDatosDePago();
            if (!this.planes) await this.cargarPreciosPlanes();
        } catch (err) {
            alert(`No se pudo iniciar la suscripción: ${err.message}`);
            return;
        }
        if (datosDePago.gateway === 'stripe') {
            // Con pasarela configurada no hay formulario propio: el pago se hace en su página.
            await this.enviarCheckout({ plan_code: planCode });
            return;
        }
        this.abrirFormularioPago(planCode, datosDePago);
    },

    // Contratación sin formulario propio: plan gratuito o pago en la página de la pasarela.
    async enviarCheckout(payload) {
        try {
            const respuesta = await ApiService.iniciarCheckoutPlan(payload);
            if (respuesta.checkout_url) {
                this._saliendoAPago = true;
                window.location.href = respuesta.checkout_url;
                return;
            }
            this.agregarLogCiudadano(`💳 ${this.escaparTexto(respuesta.message)}`);
            alert(respuesta.message);
        } catch (err) {
            alert(`No se pudo iniciar la suscripción: ${err.message}`);
        }
        await this.cargarPlanActual();
    },

    abrirFormularioPago(planCode, datosDePago) {
        const plan = (this.planes || {})[planCode];
        this._planEnPago = planCode;
        document.getElementById('modal-pago-titulo').textContent = `Activar plan ${this.NOMBRES_PLAN[planCode] || planCode}`;
        document.getElementById('modal-pago-monto').textContent = plan ? `S/ ${Number(plan.price).toFixed(2)}` : 'S/ --';
        document.getElementById('modal-pago-titular').textContent = datosDePago.account_holder;
        document.getElementById('modal-pago-destinos').innerHTML = datosDePago.methods.map((metodo) =>
            `<li><span class="text-slate-400">${this.escaparTexto(metodo.label)}:</span> <span class="font-mono">${this.escaparTexto(metodo.destination)}</span></li>`
        ).join('');
        document.getElementById('pago-metodo').innerHTML = datosDePago.methods.map((metodo) =>
            `<option value="${this.escaparTexto(metodo.code)}">${this.escaparTexto(metodo.label)}</option>`
        ).join('');
        document.getElementById('pago-referencia').value = '';
        document.getElementById('pago-feedback').textContent = '';
        document.getElementById('modal-pago').classList.remove('hidden');
        document.getElementById('pago-referencia').focus();
    },

    cerrarFormularioPago() {
        this._planEnPago = null;
        document.getElementById('modal-pago')?.classList.add('hidden');
    },

    async enviarPagoReportado(event) {
        event.preventDefault();
        const feedback = document.getElementById('pago-feedback');
        const boton = document.getElementById('pago-enviar');
        const planCode = this._planEnPago;
        if (!planCode) return;
        feedback.textContent = '';
        boton.disabled = true;
        try {
            const payload = {
                plan_code: planCode,
                payment_method: document.getElementById('pago-metodo').value,
                payment_reference: document.getElementById('pago-referencia').value.trim(),
            };
            const respuesta = await ApiService.iniciarCheckoutPlan(payload);
            this.cerrarFormularioPago();
            this.agregarLogCiudadano(`💳 ${this.escaparTexto(respuesta.message)}`);
            alert(respuesta.message);
            await this.cargarPlanActual();
        } catch (err) {
            // El formulario queda abierto para que el usuario corrija el dato.
            feedback.textContent = err.message;
        } finally {
            boton.disabled = false;
        }
    },

    async procesarPlanPendiente() {
        const planCode = sessionStorage.getItem('qgeo_pending_plan');
        if (!planCode) return;
        sessionStorage.removeItem('qgeo_pending_plan');
        this.mostrarMensajePlanes('');
        await this.contratarPlan(planCode);
    },

    // Al volver de la pasarela (?checkout=success&session_id=...) se confirma el pago en el backend.
    async procesarRetornoDePago() {
        const params = new URLSearchParams(window.location.search);
        const estado = params.get('checkout');
        if (!estado) return;
        const sessionId = params.get('session_id');
        ['checkout', 'session_id', 'plan', 'usuario'].forEach((clave) => params.delete(clave));
        history.replaceState({}, '', `${location.pathname}${params.size ? `?${params}` : ''}`);

        if (estado === 'cancel') {
            alert('Pago cancelado. Tu plan no cambió.');
            return;
        }
        if (estado !== 'success' || !sessionId) return;
        try {
            const plan = await ApiService.confirmarCheckout(sessionId);
            alert(plan.pending_plan_code
                ? 'El pago todavía no figura como completado. Tu plan se activará cuando la pasarela lo confirme.'
                : `Pago confirmado. Plan ${this.NOMBRES_PLAN[plan.plan_code] || plan.plan_code} activo.`);
        } catch (err) {
            alert(`No se pudo confirmar el pago: ${err.message}`);
        }
    },

    async cargarPlanActual() {
        const badge = document.getElementById('badge-rol');
        if (!badge || !this.usuarioActual || this.institucionActual !== 'individual') return;
        try {
            const plan = await ApiService.obtenerMiPlan();
            const nombre = this.NOMBRES_PLAN[plan.plan_code] || plan.plan_code;
            const enCurso = plan.pending_plan_code
                ? ` (${this.NOMBRES_PLAN[plan.pending_plan_code] || plan.pending_plan_code} ${plan.pending_status === 'manual_review' ? 'en validación' : 'pendiente de pago'})`
                : '';
            badge.innerText = `B2C - Ciudadano · Plan ${nombre}${enCurso}`;
            // El botón de mejora solo se ofrece a quien está en Free y no tiene un pago en revisión.
            document.getElementById('btn-mejorar-plan')?.classList.toggle(
                'hidden', plan.plan_code !== 'free' || Boolean(plan.pending_plan_code)
            );
        } catch (err) {
            console.warn('No se pudo consultar el plan:', err.message);
        }
    },

    async cargarPagosPorValidar() {
        const list = document.getElementById('owner-payments-list');
        const feedback = document.getElementById('owner-payments-feedback');
        if (!list || !sessionStorage.getItem('qgeo_owner_token')) return;
        try {
            const pagos = await ApiService.listarPagosPorValidar();
            if (feedback) feedback.textContent = `${pagos.length} pago(s) por validar`;
            if (!pagos.length) {
                list.innerHTML = '<p class="text-sm text-slate-400">No hay pagos pendientes de validación.</p>';
                return;
            }
            list.innerHTML = pagos.map((pago) => `
                <article data-owner-payment="${Number(pago.id)}" class="rounded-xl border border-slate-800 bg-slate-900 p-4 text-xs">
                    <div class="flex items-start justify-between gap-3">
                        <div>
                            <h3 class="text-sm font-bold text-white">${this.escaparTexto(pago.usuario)}</h3>
                            <p class="mt-1 text-slate-400">Plan ${this.escaparTexto(this.NOMBRES_PLAN[pago.plan_code] || pago.plan_code)} · ${this.escaparTexto(pago.currency)} ${Number(pago.price).toFixed(2)}</p>
                            <p class="mt-1 text-slate-200">${this.escaparTexto(this.NOMBRES_METODO_PAGO[pago.payment_method] || pago.payment_method || 'Sin método')} · N.º de operación: <span class="font-mono font-semibold">${this.escaparTexto(pago.payment_reference || '—')}</span></p>
                            <p class="mt-1 text-slate-500">Solicitado: ${this.escaparTexto(this.formatearFecha(pago.created_at))}</p>
                        </div>
                        <span class="rounded-md border border-amber-700 px-2 py-1 text-[10px] uppercase text-amber-200">Por validar</span>
                    </div>
                    <div class="mt-3 flex justify-end gap-2">
                        <button type="button" data-payment-action="reject" class="rounded-lg border border-red-800 px-3 py-2 text-xs text-red-300 hover:bg-red-950">Rechazar</button>
                        <button type="button" data-payment-action="approve" class="rounded-lg bg-emerald-700 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-600">Pago recibido: activar plan</button>
                    </div>
                </article>`).join('');
        } catch (error) {
            if (feedback) feedback.textContent = error.message;
            list.innerHTML = '';
        }
    },

    inicializarModuloAntirrobo() {
        const overlay = document.getElementById('anti-theft-overlay');
        if (!overlay || this._antiTheftHooked) return;

        this._antiTheftHooked = true;

        window.addEventListener('beforeunload', (event) => {
            if (this.usuarioActual && !this._saliendoAPago) {
                event.preventDefault();
                event.returnValue = '';
                this.mostrarPantallaSeñuelo(
                    'Apagando sistema...',
                    'Se está ejecutando el protocolo de protección silenciosa.'
                );
                return '';
            }
        });
    },

    mostrarPantallaSeñuelo(titulo, detalle) {
        const overlay = document.getElementById('anti-theft-overlay');
        const title = document.getElementById('anti-theft-title');
        const detail = document.getElementById('anti-theft-detail');

        if (!overlay || !title || !detail) return;
        title.textContent = titulo;
        detail.textContent = detalle;
        overlay.classList.remove('hidden');
        overlay.classList.add('flex');
    },

    ocultarPantallaSeñuelo() {
        const overlay = document.getElementById('anti-theft-overlay');
        if (overlay) {
            overlay.classList.add('hidden');
            overlay.classList.remove('flex');
        }
    },

    async capturarFotoIntruso() {
        const video = document.getElementById('anti-theft-video');
        const canvas = document.getElementById('anti-theft-canvas');

        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error('La cámara no está disponible en este navegador.');
        }

        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'user' },
            audio: false
        });

        try {
            video.srcObject = stream;
            await video.play();
            await new Promise((resolve) => setTimeout(resolve, 350));  // el primer cuadro suele salir negro

            const width = video.videoWidth || 640;
            const height = video.videoHeight || 480;
            canvas.width = width;
            canvas.height = height;

            const context = canvas.getContext('2d');
            context.drawImage(video, 0, 0, width, height);
            return canvas.toDataURL('image/jpeg', 0.9);
        } finally {
            stream.getTracks().forEach(track => track.stop());
        }
    },

    // ==========================================
    // EVIDENCIA: FOTO + UBICACIÓN AL CORREO DE SEGURIDAD
    // ==========================================
    correoSeguridadActual: null,
    _ultimaEvidenciaAutomatica: 0,
    NOMBRES_EVIDENCIA: { ANTI_THEFT: 'Antirrobo', SOS: 'SOS', PANICO: 'Pánico', LLAMADA_EMERGENCIA: 'Llamada' },

    ubicacionParaEvidencia() {
        return new Promise((resolve) => {
            if (!navigator.geolocation) {
                resolve(null);
                return;
            }
            navigator.geolocation.getCurrentPosition(
                (position) => resolve({ lat: position.coords.latitude, lng: position.coords.longitude }),
                () => resolve(null),
                { enableHighAccuracy: true, timeout: 8000, maximumAge: 30000 }
            );
        });
    },

    // Toma la foto con la cámara frontal y la envía con la ubicación. El servidor la guarda
    // en la cuenta y la manda al correo de seguridad. `ubicacion`: {lat,lng} si ya se conoce,
    // null si ya se intentó y no hay, o sin definir para pedirla ahora.
    async capturarEvidencia(tipoEvento, { ubicacion, detalle } = {}) {
        const captura = Promise.race([
            this.capturarFotoIntruso(),
            new Promise((_, reject) => setTimeout(() => reject(new Error('La cámara no respondió a tiempo.')), 12000))
        ]);
        const [fotoBase64, posicion] = await Promise.all([
            captura,
            ubicacion === undefined ? this.ubicacionParaEvidencia() : Promise.resolve(ubicacion)
        ]);
        // El usuario y el destino no viajan: el servidor usa la sesión y el correo guardado.
        const payload = { foto_base64: fotoBase64, tipo_evento: tipoEvento };
        if (detalle) payload.detalle = String(detalle).slice(0, 60);
        if (posicion && posicion.lat !== null && posicion.lng !== null) {
            payload.latitud = posicion.lat;
            payload.longitud = posicion.lng;
        }
        const data = await ApiService.enviarAlertaSeguridad(payload);
        return { ...data, conUbicacion: payload.latitud !== undefined };
    },

    // Captura en segundo plano al enviar un SOS o un pánico y al tocar un número de
    // emergencia. Solo si el usuario registró un correo de seguridad. Nunca retrasa
    // ni bloquea la alerta o la llamada: si la cámara falla, solo se anota.
    evidenciaAutomatica(tipoEvento, opciones = {}) {
        if (!this.usuarioActual || !this.correoSeguridadActual || this.rolActual !== 'ciudadano') return;
        const ahora = Date.now();
        if (ahora - this._ultimaEvidenciaAutomatica < 20000) return;  // una foto por emergencia, no una por clic
        this._ultimaEvidenciaAutomatica = ahora;
        this.capturarEvidencia(tipoEvento, opciones)
            .then((data) => {
                this.agregarLogCiudadano(`📷 Evidencia #${Number(data.alerta_id)} (${this.NOMBRES_EVIDENCIA[tipoEvento] || 'evidencia'}): ${this.escaparHtml(data.mensaje)}${data.conUbicacion ? '' : ' Sin ubicación disponible.'}`);
            })
            .catch((error) => {
                this.agregarLogCiudadano(`📷 No se pudo tomar la foto de evidencia: ${this.escaparHtml(error.message)}`);
            })
            .finally(() => {
                this.cargarEvidenciasSeguridad();
                this.actualizarBloqueoCorreoSeguridad();
            });
    },

    inicializarEvidenciaEnLlamadas() {
        if (this._llamadasHooked) return;
        this._llamadasHooked = true;
        // PNP, Bomberos, SAMU y los números de «Cerca de ti». La llamada sigue su curso
        // normal; la foto se toma en paralelo.
        document.addEventListener('click', (event) => {
            const enlace = event.target.closest && event.target.closest('a[href^="tel:"]');
            if (!enlace) return;
            this.evidenciaAutomatica('LLAMADA_EMERGENCIA', { detalle: enlace.getAttribute('href').replace('tel:', '') });
        });
    },

    async activarModoSeñueloAntirrobo() {
        if (!this.usuarioActual) {
            alert('Debe iniciar sesión para activar la protección antirrobo.');
            return;
        }

        // La pantalla falsa no revela que se está tomando una foto.
        this.mostrarPantallaSeñuelo('Apagando sistema...', 'Cerrando sesión de forma segura.');

        try {
            const data = await this.capturarEvidencia('ANTI_THEFT');
            this.agregarLogCiudadano(`🔒 Antirrobo #${Number(data.alerta_id)}: ${this.escaparHtml(data.mensaje)}${data.conUbicacion ? '' : ' Sin ubicación disponible.'}`);
        } catch (error) {
            this.agregarLogCiudadano(`❌ Antirrobo: no se guardó la evidencia: ${this.escaparHtml(error.message)}`);
        } finally {
            this.cargarEvidenciasSeguridad();
            this.actualizarBloqueoCorreoSeguridad();
            setTimeout(() => this.ocultarPantallaSeñuelo(), 2600);
        }
    },

    async actualizarBloqueoCorreoSeguridad() {
        try {
            this.mostrarEstadoCorreoSeguridad(await ApiService.obtenerContactoSeguridad());
        } catch (error) {
            // Sin conexión no cambia lo que ya se muestra.
        }
    },

    async cargarContactoSeguridad() {
        const campo = document.getElementById('correo-seguridad');
        const estado = document.getElementById('correo-seguridad-estado');
        if (!campo || !estado) return;
        try {
            const contacto = await ApiService.obtenerContactoSeguridad();
            campo.value = contacto.correo || '';
            this.mostrarEstadoCorreoSeguridad(contacto);
        } catch (error) {
            estado.textContent = `No se pudo consultar tu correo de seguridad: ${error.message}`;
            estado.className = 'min-h-[1rem] text-[11px] text-red-400';
        }
        this.cargarEvidenciasSeguridad();
    },

    mostrarEstadoCorreoSeguridad(contacto) {
        const estado = document.getElementById('correo-seguridad-estado');
        const campo = document.getElementById('correo-seguridad');
        const boton = document.getElementById('btn-guardar-correo-seguridad');
        if (!estado) return;
        this.correoSeguridadActual = contacto.correo || null;
        const bloqueado = Boolean(contacto.correo && contacto.bloqueado_hasta);
        if (campo) {
            campo.disabled = bloqueado;
            if (bloqueado) campo.value = contacto.correo;
        }
        if (boton) boton.disabled = bloqueado;

        let texto = 'Sin correo registrado: «Apagar sistema» guarda la foto solo en tu cuenta, y el SOS no toma foto.';
        let color = 'text-slate-400';
        if (contacto.correo && contacto.servidor_puede_enviar) {
            texto = `Las fotos con tu ubicación se enviarán a ${contacto.correo}.`;
            color = 'text-emerald-400';
        } else if (contacto.correo) {
            texto = 'Correo guardado. Este servidor aún no tiene correo saliente configurado, así que por ahora las fotos solo se guardan en tu cuenta.';
            color = 'text-amber-300';
        }
        if (bloqueado) {
            texto += ` Bloqueado hasta el ${this.formatearFecha(contacto.bloqueado_hasta)}: hay una alerta o evidencia reciente y el correo no se puede cambiar.`;
        }
        estado.textContent = texto;
        estado.className = `min-h-[1rem] text-[11px] ${color}`;
    },

    // Pide el permiso de cámara al guardar el correo, para que en una emergencia la
    // foto se pueda tomar sin que aparezca ninguna pregunta en pantalla.
    async prepararCamara() {
        const aviso = document.getElementById('camara-estado');
        if (!aviso) return;
        try {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error('sin cámara');
            const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false });
            stream.getTracks().forEach((track) => track.stop());
            aviso.textContent = 'Cámara autorizada: la foto se tomará sin preguntar.';
            aviso.className = 'text-[11px] text-emerald-400';
        } catch (error) {
            aviso.textContent = 'La cámara no está autorizada en este navegador: no se podrán tomar fotos hasta que la permitas.';
            aviso.className = 'text-[11px] text-amber-300';
        }
    },

    async guardarCorreoSeguridad(event) {
        event.preventDefault();
        const campo = document.getElementById('correo-seguridad');
        const estado = document.getElementById('correo-seguridad-estado');
        try {
            const contacto = await ApiService.guardarContactoSeguridad(campo.value.trim() || null);
            campo.value = contacto.correo || '';
            this.mostrarEstadoCorreoSeguridad(contacto);
            if (contacto.correo) this.prepararCamara();
        } catch (error) {
            estado.textContent = error.message;
            estado.className = 'min-h-[1rem] text-[11px] text-red-400';
        }
    },

    async cargarEvidenciasSeguridad() {
        const contenedor = document.getElementById('lista-evidencias');
        if (!contenedor) return;
        try {
            const evidencias = await ApiService.listarEvidenciasSeguridad();
            contenedor.innerHTML = evidencias.map((evidencia) => `
                <div class="flex items-center justify-between gap-2 rounded-xl border border-slate-800 bg-slate-950 px-2.5 py-2 text-[11px]">
                    <span class="text-slate-300">#${Number(evidencia.id)} · ${this.escaparHtml(this.NOMBRES_EVIDENCIA[String(evidencia.tipo_evento).split(':')[0]] || 'Evidencia')} · ${this.escaparHtml(this.formatearFecha(evidencia.creado_en))} · ${evidencia.latitud === null ? 'sin ubicación' : 'con ubicación'}${evidencia.email_enviado ? ' · correo enviado' : ''}</span>
                    <button type="button" onclick="App.verEvidencia(${Number(evidencia.id)})" class="whitespace-nowrap text-cyan-300 underline">Ver foto</button>
                </div>
            `).join('');
        } catch (error) {
            contenedor.innerHTML = '';
        }
    },

    async verEvidencia(eventoId) {
        try {
            const evidencia = await ApiService.obtenerFotoEvidencia(eventoId);
            if (!/^data:image\/(jpeg|png);base64,[A-Za-z0-9+\/=]+$/.test(evidencia.foto)) throw new Error('La evidencia guardada no es una imagen válida.');
            document.getElementById('modal-evidencia-foto').src = evidencia.foto;
            document.getElementById('modal-evidencia-titulo').textContent = `Evidencia antirrobo #${Number(evidencia.id)}`;
            const modal = document.getElementById('modal-evidencia');
            modal.classList.remove('hidden');
            modal.classList.add('flex');
        } catch (error) {
            alert(`No se pudo abrir la foto: ${error.message}`);
        }
    },

    cerrarEvidencia() {
        const modal = document.getElementById('modal-evidencia');
        if (!modal) return;
        modal.classList.add('hidden');
        modal.classList.remove('flex');
        document.getElementById('modal-evidencia-foto').removeAttribute('src');
    },

    async verificarSaludBackend() {
        const indicador = document.getElementById('indicador-servidor');
        try {
            await ApiService.verificarSalud();
            if (indicador) {
                indicador.className = "w-2 h-2 rounded-full bg-emerald-500 inline-block animate-pulse";
                indicador.title = "Backend FastAPI conectado";
            }
        } catch (e) {
            if (indicador) {
                indicador.className = "w-2 h-2 rounded-full bg-amber-500 inline-block";
                indicador.title = "Backend desconectado o modo local";
            }
        }
    },

    async verificarSesionPrevia() {
        if (sessionStorage.getItem('qgeo_owner_token')) {
            this.cerrarSesion();
            return;
        }
        const flowVersion = this._authFlowVersion;
        const usuarioGuardado = localStorage.getItem(CONFIG.STORAGE_KEYS.USER);
        const rolGuardado = localStorage.getItem(CONFIG.STORAGE_KEYS.ROLE);
        const codigoGuardado = localStorage.getItem(CONFIG.STORAGE_KEYS.CODE);
        const institucionGuardada = localStorage.getItem(CONFIG.STORAGE_KEYS.INSTITUTION);
        const tokenGuardado = localStorage.getItem(CONFIG.STORAGE_KEYS.TOKEN);

        if (usuarioGuardado && rolGuardado && tokenGuardado) {
            try {
                const account = await ApiService.verificarSesion();
                if (flowVersion !== this._authFlowVersion) return;
                localStorage.setItem(CONFIG.STORAGE_KEYS.USER, account.usuario);
                localStorage.setItem(CONFIG.STORAGE_KEYS.ROLE, account.rol);
                localStorage.setItem(CONFIG.STORAGE_KEYS.INSTITUTION, account.institucion || 'individual');
                if (account.codigo_enlace) {
                    localStorage.setItem(CONFIG.STORAGE_KEYS.CODE, account.codigo_enlace);
                }
                this.iniciarSesionEnUI(
                    account.usuario,
                    account.rol,
                    account.codigo_enlace || codigoGuardado,
                    account.institucion || institucionGuardada
                );
            } catch (error) {
                if (flowVersion !== this._authFlowVersion) return;
                this.cerrarSesion();
            }
        } else {
            this.cerrarSesion();
        }
    },

    cambiarTabAuth(tab) {
        const formLogin = document.getElementById('form-login');
        const formRegistro = document.getElementById('form-registro');
        const tabLogin = document.getElementById('tab-login');
        const tabRegistro = document.getElementById('tab-registro');

        if (tab === 'login') {
            formLogin.classList.remove('hidden');
            formRegistro.classList.add('hidden');
            tabLogin.className = "py-2.5 font-semibold text-xs rounded-lg text-white bg-slate-800 transition";
            tabRegistro.className = "py-2.5 font-semibold text-xs rounded-lg text-slate-400 hover:text-white transition";
        } else {
            formLogin.classList.add('hidden');
            formRegistro.classList.remove('hidden');
            tabRegistro.className = "py-2.5 font-semibold text-xs rounded-lg text-white bg-slate-800 transition";
            tabLogin.className = "py-2.5 font-semibold text-xs rounded-lg text-slate-400 hover:text-white transition";
        }
    },

    cambiarModoRegistro(modo) {
        const institucional = modo === 'institucional';
        const familiarButton = document.getElementById('registro-modo-familiar');
        const institutionalButton = document.getElementById('registro-modo-institucional');
        const institutionField = document.getElementById('registro-institucion-campo');
        document.getElementById('registro-modo').value = institucional ? 'institucional' : 'familiar';
        familiarButton.setAttribute('aria-pressed', String(!institucional));
        institutionalButton.setAttribute('aria-pressed', String(institucional));
        familiarButton.className = institucional
            ? 'py-2.5 font-semibold text-xs rounded-lg text-slate-400 hover:text-white transition'
            : 'py-2.5 font-semibold text-xs rounded-lg text-white bg-slate-800 transition';
        institutionalButton.className = institucional
            ? 'py-2.5 font-semibold text-xs rounded-lg text-white bg-slate-800 transition'
            : 'py-2.5 font-semibold text-xs rounded-lg text-slate-400 hover:text-white transition';
        institutionField.classList.toggle('hidden', !institucional);
        [
            'reg-institucion',
            'reg-ruc',
            'reg-tipo-institucion',
            'reg-region-institucion',
            'reg-correo-institucion',
            'reg-contacto-institucion',
            'reg-telefono-institucion',
            'reg-evidencia-institucion',
        ].forEach((id) => {
            document.getElementById(id).required = institucional;
        });
    },

    cambiarModoLogin(modo) {
        const institucional = modo === 'institucional';
        const botonFamiliar = document.getElementById('login-modo-familiar');
        const botonInstitucional = document.getElementById('login-modo-institucional');
        document.getElementById('login-modo').value = institucional ? 'institucional' : 'familiar';
        botonFamiliar.setAttribute('aria-pressed', String(!institucional));
        botonInstitucional.setAttribute('aria-pressed', String(institucional));
        botonFamiliar.className = institucional
            ? 'py-2.5 font-semibold text-xs rounded-lg text-slate-400 hover:text-white transition'
            : 'py-2.5 font-semibold text-xs rounded-lg text-white bg-slate-800 transition';
        botonInstitucional.className = institucional
            ? 'py-2.5 font-semibold text-xs rounded-lg text-white bg-slate-800 transition'
            : 'py-2.5 font-semibold text-xs rounded-lg text-slate-400 hover:text-white transition';
        document.getElementById('login-modo-descripcion').textContent = institucional
            ? 'Acceso del personal autorizado a la cuenta de su institución.'
            : 'Acceso ciudadano y red familiar.';
        document.getElementById('login-usuario-label').textContent = institucional
            ? 'Correo o usuario institucional'
            : 'Usuario familiar';
        document.getElementById('login-usuario').placeholder = institucional
            ? 'Correo asignado por la institución'
            : 'Ej. standy_cerna';
        document.getElementById('login-feedback').textContent = '';
    },

    async manejarLogin(event) {
        event.preventDefault();
        this._authFlowVersion += 1;
        const usuario = document.getElementById('login-usuario').value.trim();
        const password = document.getElementById('login-password').value.trim();
        const feedback = document.getElementById('login-feedback');

        feedback.innerHTML = `<span class="text-slate-400">Verificando en base de datos...</span>`;

        try {
            const modo = document.getElementById('login-modo').value;
            const data = await ApiService.loginUsuario({ usuario, password, modo });
            feedback.innerHTML = `<span class="text-emerald-400">✅ Acceso autorizado</span>`;
            
            localStorage.setItem(CONFIG.STORAGE_KEYS.USER, data.usuario);
            localStorage.setItem(CONFIG.STORAGE_KEYS.ROLE, data.rol);
            localStorage.setItem(CONFIG.STORAGE_KEYS.TOKEN, data.token);
            localStorage.setItem(CONFIG.STORAGE_KEYS.INSTITUTION, data.institucion || 'individual');
            if (data.codigo_enlace) {
                localStorage.setItem(CONFIG.STORAGE_KEYS.CODE, data.codigo_enlace);
            }

            setTimeout(() => {
                this.iniciarSesionEnUI(data.usuario, data.rol, data.codigo_enlace, data.institucion);
            }, 400);
        } catch (err) {
            feedback.innerHTML = `<span class="text-red-400">❌ ${this.escaparTexto(err.message)}</span>`;
        }
    },

    async manejarRegistro(event) {
        event.preventDefault();
        this._authFlowVersion += 1;
        const flowVersion = this._authFlowVersion;
        const usuario = document.getElementById('reg-usuario').value.trim();
        const password = document.getElementById('reg-password').value.trim();
        const modo = document.getElementById('registro-modo').value;
        const nombreInstitucion = document.getElementById('reg-institucion').value.trim();
        const feedback = document.getElementById('reg-feedback');

        feedback.innerHTML = `<span class="text-slate-400">Registrando con hash seguro...</span>`;

        try {
            const data = await ApiService.registrarUsuario({
                usuario,
                password,
                modo,
                nombre_institucion: modo === 'institucional' ? nombreInstitucion : null,
                ruc_institucion: modo === 'institucional' ? document.getElementById('reg-ruc').value.trim() : null,
                tipo_institucion: modo === 'institucional' ? document.getElementById('reg-tipo-institucion').value.trim() : null,
                region_institucion: modo === 'institucional' ? document.getElementById('reg-region-institucion').value.trim() : null,
                correo_institucional: modo === 'institucional' ? document.getElementById('reg-correo-institucion').value.trim() : null,
                contacto_institucional: modo === 'institucional' ? document.getElementById('reg-contacto-institucion').value.trim() : null,
                telefono_institucional: modo === 'institucional' ? document.getElementById('reg-telefono-institucion').value.trim() : null,
                evidencia_institucional_url: modo === 'institucional' ? document.getElementById('reg-evidencia-institucion').value.trim() : null
            });
            if (flowVersion !== this._authFlowVersion) return;
            if (modo === 'institucional') {
                this.cerrarSesion();
                this.cambiarTabAuth('login');
                this.cambiarModoLogin('institucional');
                document.getElementById('login-usuario').value = usuario;
                document.getElementById('login-feedback').innerHTML = `<span class="text-amber-300">${this.escaparTexto(data.mensaje)}</span>`;
                return;
            }
            feedback.innerHTML = `<span class="text-emerald-400">✅ Registrado con éxito. Tu código es <b>${data.codigo_enlace}</b></span>`;
            
            setTimeout(() => {
                this.cambiarTabAuth('login');
                document.getElementById('login-usuario').value = usuario;
                feedback.innerHTML = '';
            }, 2500);
        } catch (err) {
            feedback.innerHTML = `<span class="text-red-400">❌ ${this.escaparTexto(err.message)}</span>`;
        }
    },

    iniciarSesionEnUI(usuario, rol, codigoEnlace, institucion = 'individual') {
        this.usuarioActual = usuario;
        this.rolActual = String(rol || 'ciudadano').toLowerCase();
        this.institucionActual = institucion || 'individual';

        document.getElementById('pantalla-auth').classList.add('hidden');
        document.getElementById('pantalla-dashboard').classList.remove('hidden');
        document.getElementById('lbl-usuario').innerText = usuario;
        
        const badgeRol = document.getElementById('badge-rol');
        const esInstitucional = this.rolActual !== 'ciudadano' && this.institucionActual !== 'individual';
        badgeRol.innerText = esInstitucional ? `Institucional - ${this.rolActual}` : 'B2C - Ciudadano';

        if (esInstitucional) {
            document.getElementById('b2g-institucion').innerText = this.institucionActual;
            this.configurarVistaB2G();
            document.getElementById('institucion-nombre').value = this.institucionActual;
            this.cargarCuentaInstitucional();
            this.cargarUsuariosInstitucionales(this.institucionActual);
            this.conectarTiempoRealInstitucional();
            sessionStorage.removeItem('qgeo_pending_plan');
        } else {
            this.socketInstitucional?.close();
            this.configurarVistaCiudadano(codigoEnlace);
            this.procesarRetornoDePago()
                .then(() => this.procesarPlanPendiente())
                .then(() => this.cargarPlanActual());
        }
    },

    cerrarSesion() {
        this._authFlowVersion += 1;
        localStorage.removeItem(CONFIG.STORAGE_KEYS.USER);
        localStorage.removeItem(CONFIG.STORAGE_KEYS.ROLE);
        localStorage.removeItem(CONFIG.STORAGE_KEYS.CODE);
        localStorage.removeItem(CONFIG.STORAGE_KEYS.TOKEN);
        localStorage.removeItem(CONFIG.STORAGE_KEYS.INSTITUTION);

        clearInterval(this.timerCuentaRegresiva);
        this.usuarioActual = null;
        this.rolActual = null;
        this.institucionActual = null;
        this.socketInstitucional?.close();
        this.socketInstitucional = null;

        this.cerrarFormularioPago();
        this.cerrarEvidencia();
        ['lista-evidencias', 'invitaciones-enviadas', 'numeros-cercanos'].forEach((id) => {
            const elemento = document.getElementById(id);
            if (elemento) elemento.innerHTML = '';
        });
        const correoSeguridad = document.getElementById('correo-seguridad');
        if (correoSeguridad) {
            correoSeguridad.value = '';
            correoSeguridad.disabled = false;
        }
        this.correoSeguridadActual = null;
        this._ultimaEvidenciaAutomatica = 0;
        document.getElementById('btn-mejorar-plan')?.classList.add('hidden');
        document.getElementById('pantalla-dashboard').classList.add('hidden');
        document.getElementById('pantalla-auth').classList.remove('hidden');
        document.getElementById('login-password').value = '';
    },

    // ==========================================
    // SECCIÓN B2C: CIUDADANO, PRIVACIDAD & SISMO
    // ==========================================
    configurarVistaCiudadano(codigoEnlace) {
        document.getElementById('vista-ciudadano').classList.remove('hidden');
        document.getElementById('vista-institucion').classList.add('hidden');

        if (codigoEnlace) {
            document.getElementById('codigo-enlace-lbl').innerText = `Mi Código: ${codigoEnlace}`;
        }

        this.inicializarMapaCiudadano();
        this.cargarFamiliares();
        this.cargarContactoSeguridad();
        this.cargarDirectorioEmergencia();
    },

    inicializarMapaCiudadano() {
        if (!this.mapaCiudadano) {
            setTimeout(() => {
                const { lat, lng } = CONFIG.DEFAULT_COORDS;
                this.mapaCiudadano = L.map('mapa-ciudadano').setView([lat, lng], 14);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    maxZoom: 19,
                    attribution: '© OpenStreetMap - QuantumGeoRescue'
                }).addTo(this.mapaCiudadano);
            }, 300);
        } else {
            setTimeout(() => this.mapaCiudadano.invalidateSize(), 300);
        }
    },

    async cargarFamiliares() {
        const contenedor = document.getElementById('lista-familiares');
        if (!contenedor || !this.usuarioActual) return;
        contenedor.innerHTML = `<div class="text-xs text-slate-500">Cargando vínculos consentidos...</div>`;

        try {
            const familiares = await ApiService.listarFamiliares(this.usuarioActual);
            if (!familiares || familiares.length === 0) {
                contenedor.innerHTML = `<div class="text-xs text-slate-500 italic p-2 bg-slate-950 rounded-xl border border-slate-800">No hay vínculos aceptados. La otra cuenta debe aceptar la invitación.</div>`;
            } else {
                contenedor.innerHTML = familiares.map(f => `
                    <div class="flex justify-between items-center bg-slate-950 p-2.5 rounded-xl border border-slate-800 text-xs">
                        <div>
                            <div class="font-bold text-slate-200">${this.escaparHtml(f.nombre)}</div>
                            <div class="text-[10px] text-slate-400">${this.escaparHtml(f.parentesco)} · Vínculo consentido</div>
                        </div>
                        <button type="button" onclick="App.revocarVinculoFamiliar(${Number(f.id)})" class="text-[10px] text-red-300 underline">Revocar</button>
                    </div>
                `).join('');
            }

            await Promise.all([
                this.cargarInvitacionesFamiliares(),
                this.cargarInvitacionesEnviadas(),
                this.cargarBuzonFamiliar()
            ]);
        } catch (e) {
            // Se muestra la causa: "Error al cargar" a secas no deja saber qué revisar.
            contenedor.innerHTML = `<div class="text-xs text-red-400">No se pudo cargar tu red familiar: ${this.escaparHtml(e.message)}</div>`;
        }
    },

    async agregarFamiliar(event) {
        event.preventDefault();
        const campoCodigo = document.getElementById('fam-codigo');
        const campoParentesco = document.getElementById('fam-parentesco');
        const feedback = document.getElementById('fam-feedback');
        const codigo = campoCodigo.value.trim().toUpperCase();
        const parentesco = campoParentesco.value.trim();
        const miCodigo = (localStorage.getItem(CONFIG.STORAGE_KEYS.CODE) || '').toUpperCase();

        const avisar = (texto, esError) => {
            feedback.textContent = texto;
            feedback.className = `min-h-[1rem] text-[11px] ${esError ? 'text-red-400' : 'text-emerald-400'}`;
        };
        if (codigo && codigo === miCodigo) {
            avisar('Ese es tu propio código. Necesitas el código de tu familiar.', true);
            return;
        }

        try {
            const invitacion = await ApiService.registrarFamiliar({
                codigo_invitado: codigo,
                parentesco
            });
            campoCodigo.value = '';
            campoParentesco.value = '';
            avisar('Invitación enviada. El vínculo existirá cuando la otra persona la acepte.', false);
            this.agregarLogCiudadano(`Invitación familiar #${Number(invitacion.id)}: ${this.escaparHtml(invitacion.estado)}. Aún no existe vínculo ni se comparte ubicación.`);
            await this.cargarFamiliares();
        } catch (err) {
            avisar(err.message, true);
        }
    },

    async copiarMiCodigo() {
        const codigo = localStorage.getItem(CONFIG.STORAGE_KEYS.CODE);
        const etiqueta = document.getElementById('codigo-enlace-lbl');
        if (!codigo || !etiqueta) return;
        try {
            await navigator.clipboard.writeText(codigo);
            etiqueta.innerText = 'Código copiado';
        } catch (error) {
            etiqueta.innerText = `Mi Código: ${codigo}`;
            return;
        }
        window.setTimeout(() => { etiqueta.innerText = `Mi Código: ${codigo}`; }, 1500);
    },

    async cargarInvitacionesEnviadas() {
        const contenedor = document.getElementById('invitaciones-enviadas');
        if (!contenedor) return;
        const enviadas = await ApiService.listarInvitacionesEnviadas();
        contenedor.innerHTML = enviadas.map(inv => `
            <div class="rounded-xl border border-slate-800 bg-slate-950 p-2.5 text-xs">
                <div class="text-slate-200">Invitación a ${this.escaparHtml(inv.invitado_usuario)} como ${this.escaparHtml(inv.parentesco)}</div>
                <div class="text-[10px] text-amber-300">Pendiente: aún no la acepta.</div>
            </div>
        `).join('');
    },

    escaparHtml(valor) {
        return String(valor ?? '').replace(/[&<>"']/g, caracter => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        })[caracter]);
    },

    async cargarInvitacionesFamiliares() {
        const contenedor = document.getElementById('invitaciones-familiares');
        if (!contenedor) return;
        const invitaciones = await ApiService.listarInvitacionesFamiliares();
        if (!invitaciones.length) {
            contenedor.innerHTML = '';
            return;
        }
        contenedor.innerHTML = invitaciones.map(inv => `
            <div class="rounded-xl border border-amber-800/60 bg-amber-950/30 p-3 text-xs">
                <div class="text-slate-200">${this.escaparHtml(inv.invitante_usuario)} te invita como ${this.escaparHtml(inv.parentesco)}.</div>
                <div class="mt-2 flex gap-2">
                    <button type="button" onclick="App.responderInvitacionFamiliar(${Number(inv.id)}, true)" class="rounded bg-emerald-700 px-3 py-1.5 font-bold text-white">Aceptar y consentir</button>
                    <button type="button" onclick="App.responderInvitacionFamiliar(${Number(inv.id)}, false)" class="rounded bg-slate-700 px-3 py-1.5 text-white">Rechazar</button>
                </div>
            </div>
        `).join('');
    },

    async responderInvitacionFamiliar(id, aceptar) {
        try {
            await ApiService.responderInvitacionFamiliar(id, aceptar);
            await this.cargarFamiliares();
        } catch (error) {
            alert(`No se pudo responder la invitación: ${error.message}`);
        }
    },

    async revocarVinculoFamiliar(id) {
        try {
            await ApiService.revocarVinculoFamiliar(id);
            await this.cargarFamiliares();
        } catch (error) {
            alert(`No se pudo revocar el vínculo: ${error.message}`);
        }
    },

    async cargarBuzonFamiliar() {
        const contenedor = document.getElementById('buzon-alertas-familiares');
        if (!contenedor) return;
        const alertas = await ApiService.listarBuzonFamiliar();
        if (!alertas.length) {
            contenedor.innerHTML = '<p class="text-xs text-slate-500">No hay alertas disponibles en tu buzón.</p>';
            return;
        }
        contenedor.innerHTML = alertas.map(alerta => {
            const posicion = alerta.latitud === null || alerta.longitud === null
                ? 'Ubicación no disponible'
                : `Ubicación durante la alerta: ${Number(alerta.latitud).toFixed(4)}, ${Number(alerta.longitud).toFixed(4)}`;
            return `<article class="rounded-xl border border-red-900/70 bg-slate-950 p-3 text-xs">
                <div class="font-bold text-red-300">Alerta #${Number(alerta.id)} · ${this.escaparHtml(alerta.tipo_emergencia)}</div>
                <div class="mt-1 text-slate-300">Disponible en el buzón; lectura o atención no confirmadas.</div>
                <div class="mt-1 text-slate-400">${this.escaparHtml(posicion)}</div>
            </article>`;
        }).join('');
    },

    // ==========================================
    // NÚMEROS LOCALES «CERCA DE TI»
    // ==========================================
    CLAVE_DIRECTORIO: 'qgeo_directorio_emergencia',
    DISTANCIA_MAXIMA_CERCANOS_KM: 50,
    ETIQUETAS_CERCANOS: {
        COMISARIA: 'Comisaría más cercana', BOMBEROS: 'Bomberos más cercanos',
        SALUD: 'Salud más cercana', SERENAZGO: 'Serenazgo más cercano', OTRO: 'Otro punto cercano'
    },

    distanciaKm(lat1, lng1, lat2, lng2) {
        const rad = (grados) => grados * Math.PI / 180;
        const dLat = rad(lat2 - lat1);
        const dLng = rad(lng2 - lng1);
        const a = Math.sin(dLat / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLng / 2) ** 2;
        return 2 * 6371.0088 * Math.asin(Math.min(1, Math.sqrt(a)));
    },

    // Por cada tipo devuelve el punto más cercano y, si ese no tiene teléfono, también
    // el más cercano que sí lo tenga. Más allá del límite no se muestra nada: sería engañoso.
    puntosMasCercanos(lat, lng, puntos) {
        const mejores = {};
        for (const punto of puntos || []) {
            if (!Number.isFinite(punto.latitud) || !Number.isFinite(punto.longitud)) continue;
            const distancia = this.distanciaKm(lat, lng, punto.latitud, punto.longitud);
            if (distancia > this.DISTANCIA_MAXIMA_CERCANOS_KM) continue;
            const grupo = mejores[punto.tipo] || (mejores[punto.tipo] = { cercano: null, conTelefono: null });
            if (!grupo.cercano || distancia < grupo.cercano.distancia) grupo.cercano = { punto, distancia };
            if (punto.telefono && (!grupo.conTelefono || distancia < grupo.conTelefono.distancia)) {
                grupo.conTelefono = { punto, distancia };
            }
        }
        return Object.keys(this.ETIQUETAS_CERCANOS).filter((tipo) => mejores[tipo]).map((tipo) => {
            const { cercano, conTelefono } = mejores[tipo];
            // Si el más cercano tiene teléfono no hace falta una segunda opción.
            const alternativa = cercano.punto.telefono || !conTelefono ? null : conTelefono;
            return { punto: cercano.punto, distancia: cercano.distancia, alternativa };
        });
    },

    leerDirectorioGuardado() {
        try {
            const guardado = JSON.parse(localStorage.getItem(this.CLAVE_DIRECTORIO) || 'null');
            return guardado && Array.isArray(guardado.puntos) ? guardado : null;
        } catch (error) {
            return null;
        }
    },

    // Descarga el directorio (o confirma que la copia local sigue vigente) y lo deja
    // guardado en el dispositivo para poder usarlo sin conexión.
    async cargarDirectorioEmergencia() {
        const guardado = this.leerDirectorioGuardado();
        try {
            const respuesta = await ApiService.obtenerDirectorioEmergencia(guardado ? guardado.version : null);
            if (respuesta.sin_cambios && guardado) {
                this.directorioEmergencia = guardado;
            } else {
                this.directorioEmergencia = { version: respuesta.version, puntos: respuesta.puntos || [], descargado_en: new Date().toISOString() };
                try {
                    localStorage.setItem(this.CLAVE_DIRECTORIO, JSON.stringify(this.directorioEmergencia));
                } catch (error) {
                    console.warn('El directorio no cabe en el almacenamiento local; se usará solo en esta sesión.');
                }
            }
        } catch (error) {
            this.directorioEmergencia = guardado || { version: null, puntos: [], descargado_en: null };
        }
        return this.directorioEmergencia;
    },

    avisarNumerosCercanos(texto, esError = false) {
        const estado = document.getElementById('numeros-cercanos-estado');
        if (!estado) return;
        estado.textContent = texto;
        estado.className = `mt-1 text-[10px] leading-relaxed ${esError ? 'text-red-300' : 'text-slate-400'}`;
    },

    async renderNumerosCercanos(lat, lng) {
        const contenedor = document.getElementById('numeros-cercanos');
        if (!contenedor || !Number.isFinite(lat) || !Number.isFinite(lng)) return;
        const directorio = this.directorioEmergencia || await this.cargarDirectorioEmergencia();
        if (!directorio.puntos.length) {
            contenedor.innerHTML = '';
            this.avisarNumerosCercanos('Aún no hay números locales cargados. Usa los números nacionales de arriba.');
            return;
        }
        const cercanos = this.puntosMasCercanos(lat, lng, directorio.puntos);
        if (!cercanos.length) {
            contenedor.innerHTML = '';
            this.avisarNumerosCercanos(`No hay puntos registrados a menos de ${this.DISTANCIA_MAXIMA_CERCANOS_KM} km. Usa los números nacionales de arriba.`);
            return;
        }
        const hoy = Date.now();
        const textoDistancia = (km) => (km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(1).replace('.', ',')} km`);
        const numeroMarcable = (telefono) => String(telefono || '').replace(/[^0-9+]/g, '');
        const fechaCorta = (iso) => iso.split('-').reverse().join('/');
        const esAntiguo = (iso) => Math.floor((hoy - new Date(`${iso}T00:00:00`).getTime()) / 86400000) > 180;
        const verificacion = (punto) => `<div class="mt-1 text-[10px] ${esAntiguo(punto.verificado_en) ? 'text-amber-300' : 'text-slate-500'}">Dato verificado el ${this.escaparHtml(fechaCorta(punto.verificado_en))}${esAntiguo(punto.verificado_en) ? ' · puede estar desactualizado' : ''}</div>`;
        const dondeQueda = (punto, distancia) => {
            // La dirección suele incluir ya el distrito; no se repite.
            const direccion = punto.direccion || '';
            const repetido = punto.distrito && direccion.toLowerCase().includes(punto.distrito.toLowerCase());
            const lugar = [direccion, repetido ? '' : punto.distrito].filter(Boolean).join(', ');
            const distanciaTexto = punto.ubicacion_aproximada
                ? `A unos ${textoDistancia(distancia)} (ubicación aproximada: la del poblado)`
                : `A ${textoDistancia(distancia)} en línea recta`;
            return `${distanciaTexto}${lugar ? ` · ${this.escaparHtml(lugar)}` : ''}`;
        };
        const botonLlamar = (punto) => `<a href="tel:${numeroMarcable(punto.telefono)}" class="block rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-center font-bold text-white hover:bg-slate-700">Llamar ${this.escaparHtml(punto.telefono)}</a>`;

        contenedor.innerHTML = cercanos.map(({ punto, distancia, alternativa }) => `
                <div class="flex flex-col rounded-lg border border-slate-700 bg-slate-950 p-3 text-xs">
                    <div class="text-[10px] font-bold uppercase tracking-wide text-amber-300">${this.ETIQUETAS_CERCANOS[punto.tipo] || 'Punto cercano'}</div>
                    <div class="mt-0.5 font-bold text-white">${this.escaparHtml(punto.nombre)}</div>
                    <div class="text-[10px] text-slate-400">${dondeQueda(punto, distancia)}</div>
                    <div class="mt-auto pt-2">
                        ${punto.telefono
                            ? `${botonLlamar(punto)}${verificacion(punto)}`
                            : `<div class="rounded-lg border border-slate-800 px-3 py-2 text-center text-[11px] text-slate-400">Sin teléfono registrado</div>${verificacion(punto)}`}
                    </div>
                    ${alternativa ? `
                    <div class="mt-2 border-t border-slate-800 pt-2">
                        <div class="text-[10px] font-bold uppercase tracking-wide text-slate-400">Con teléfono más cerca</div>
                        <div class="font-semibold text-slate-200">${this.escaparHtml(alternativa.punto.nombre)}</div>
                        <div class="mb-1.5 text-[10px] text-slate-400">${dondeQueda(alternativa.punto, alternativa.distancia)}</div>
                        ${botonLlamar(alternativa.punto)}${verificacion(alternativa.punto)}
                    </div>` : ''}
                </div>`).join('');
        this.avisarNumerosCercanos('Calculado en este dispositivo: tu ubicación no se envió. Si no contestan, llama a los números nacionales.');
    },

    async mostrarNumerosCercanos() {
        if (!navigator.geolocation) {
            this.avisarNumerosCercanos('Este dispositivo no entrega ubicación. Usa los números nacionales de arriba.', true);
            return;
        }
        this.avisarNumerosCercanos('Obteniendo tu ubicación…');
        navigator.geolocation.getCurrentPosition(
            (posicion) => this.renderNumerosCercanos(posicion.coords.latitude, posicion.coords.longitude),
            () => this.avisarNumerosCercanos('No se pudo obtener tu ubicación. Usa los números nacionales de arriba.', true),
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
        );
    },

    simularSismo() {
        const estadoSensor = document.getElementById('estado-sensor');
        const cajaConteo = document.getElementById('caja-conteo');
        const lblSegundos = document.getElementById('lbl-segundos');

        estadoSensor.innerText = "⚠️ ¡Movimiento inercial violento detectado (Magnitud 6.8)!";
        estadoSensor.className = "text-xs text-red-400 font-bold animate-pulse";
        cajaConteo.classList.remove('hidden');

        this.segundosRestantes = 10;
        lblSegundos.innerText = this.segundosRestantes;

        clearInterval(this.timerCuentaRegresiva);
        this.timerCuentaRegresiva = setInterval(() => {
            this.segundosRestantes--;
            lblSegundos.innerText = this.segundosRestantes;

            if (this.segundosRestantes <= 0) {
                clearInterval(this.timerCuentaRegresiva);
                cajaConteo.classList.add('hidden');
                estadoSensor.innerText = "🚨 Simulacro: sin respuesta al conteo, se registró la alerta de prueba.";
                estadoSensor.className = "text-xs text-red-500 font-bold";
                // Es una sacudida simulada con el botón: se marca como simulacro para
                // que no llegue a la bandeja de ninguna institución.
                this.ejecutarDespachoAlerta("Alerta Sísmica Inercial", 5, {
                    origen_alerta: 'AUTOMATICO_INERCIA',
                    estado_confirmacion: 'EXPIRADO_INCONSCIENTE',
                    es_simulacro: true
                });
            }
        }, 1000);
    },

    confirmarEstoyBien() {
        clearInterval(this.timerCuentaRegresiva);
        document.getElementById('caja-conteo').classList.add('hidden');
        const estadoSensor = document.getElementById('estado-sensor');
        estadoSensor.innerText = "✅ Movimiento cancelado. El usuario confirmó encontrarse a salvo.";
        estadoSensor.className = "text-xs text-emerald-400 font-medium";

        this.agregarLogCiudadano("Usuario reportó 'Estoy Bien'. Se evitó el despacho de rescate.");
    },

    obtenerUbicacionReal(callback, mensaje = 'Obteniendo ubicación real...') {
        const indicador = document.getElementById('estado-panic-silencioso');
        if (indicador) {
            indicador.innerHTML = mensaje;
            indicador.className = 'text-[11px] text-amber-300 bg-slate-950 border border-amber-800 rounded-xl p-2';
        }

        if (!navigator.geolocation) {
            callback({
                lat: null,
                lng: null,
                fallback: true
            });
            return;
        }

        navigator.geolocation.getCurrentPosition((position) => {
            callback({
                lat: position.coords.latitude,
                lng: position.coords.longitude,
                fallback: false
            });
        }, () => {
            callback({
                lat: null,
                lng: null,
                fallback: true
            });
        }, {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0
        });
    },

    async activarPanicSilencioso(detectadoPorVoz = false, fraseDetectada = '') {
        const latLng = await new Promise((resolve) => {
            this.obtenerUbicacionReal((resultado) => resolve(resultado), detectadoPorVoz ? '⚠️ Amenaza detectada por voz. Obteniendo ubicación real...' : '📍 Obteniendo ubicación actual para protocolo silencioso...');
        });

        const tipo = detectadoPorVoz ? 'ROBO_ASALTO_COACCION (voz)' : 'ROBO_ASALTO_COACCION (manual)';
        this.geolocalizacionActual = latLng;
        if (latLng.lat !== null && latLng.lng !== null) this.renderNumerosCercanos(latLng.lat, latLng.lng);
        this.evidenciaAutomatica('PANICO', { ubicacion: latLng.lat === null || latLng.lng === null ? null : { lat: latLng.lat, lng: latLng.lng } });

        try {
            const payload = {
                client_alert_id: await ApiService.obtenerClientAlertId(),
                usuario: this.usuarioActual,
                dispositivo_id: this.usuarioActual,
                tipo_amenaza: detectadoPorVoz ? 'coaccion_voz' : 'panic_silencioso',
                descripcion: detectadoPorVoz ? `Frase detectada: "${fraseDetectada}"` : 'Activación manual segura de pánico silencioso.',
                amenaza_detectada: true,
                activar_panic_silencioso: true,
                nivel_gravedad: 5,
                latitud: latLng.lat,
                longitud: latLng.lng,
                timestamp_dispositivo: new Date().toISOString()
            };
            const data = await ApiService.alertaCoaccion(payload);
            this.actualizarBloqueoCorreoSeguridad();
            document.getElementById('coords-ciudadano').innerText = latLng.lat === null || latLng.lng === null
                ? 'Ubicación no disponible'
                : `Lat: ${latLng.lat.toFixed(4)}, Lng: ${latLng.lng.toFixed(4)}`;

            const indicador = document.getElementById('estado-panic-silencioso');
            if (indicador) {
                indicador.textContent = `Alerta #${data.alerta_id} registrada. ${this.describirEstadoInstitucional(data.enrutamiento_institucional)}${latLng.fallback ? ' No se obtuvo ubicación; no se usó una ubicación de reemplazo.' : ' Ubicación capturada durante la alerta.'}`;
                indicador.className = 'text-[11px] text-red-300 bg-red-950 border border-red-800 rounded-xl p-2';
            }

            this.agregarLogCiudadano(`Alerta #${Number(data.alerta_id)} guardada en el servidor como ${tipo}. ${this.escaparHtml(this.describirEstadoInstitucional(data.enrutamiento_institucional))}`);

            if (this.mapaCiudadano && latLng.lat !== null && latLng.lng !== null) {
                if (this.marcadorCiudadano) this.mapaCiudadano.removeLayer(this.marcadorCiudadano);
                this.marcadorCiudadano = L.marker([latLng.lat, latLng.lng], {
                    icon: L.divIcon({
                        html: '<div style="background:#a855f7;border:2px solid white;border-radius:999px;width:14px;height:14px;box-shadow:0 0 12px rgba(168,85,247,.9);"></div>',
                        className: '',
                        iconSize: [14, 14]
                    })
                }).addTo(this.mapaCiudadano)
                    .bindPopup(`<b>🚨 Pánico Silencioso</b><br>Tipo: Robo/Asalto/Coacción`)
                    .openPopup();
                this.mapaCiudadano.setView([latLng.lat, latLng.lng], 15);
            }

            if (this.mapaB2G) {
                this.cargarAlertasB2G();
            }
        } catch (err) {
            const indicador = document.getElementById('estado-panic-silencioso');
            if (indicador) {
                indicador.innerHTML = err.alertaLocalGuardada
                    ? 'Sin confirmación del servidor. La alerta quedó guardada en este dispositivo para reintento; llama a un número visible en SOS si necesitas respuesta inmediata.'
                    : `❌ No se pudo guardar la alerta SOS: ${err.message}`;
                indicador.className = 'text-[11px] text-red-300 bg-red-950 border border-red-800 rounded-xl p-2';
            }
            this.agregarLogCiudadano(`❌ Error al activar pánico silencioso: ${err.message}`);
        }
    },

    dispararAlertaManual() {
        this.ejecutarDespachoAlerta("Alerta SOS Manual", 4);
    },

    // Texto de lo que realmente pasó con la alerta del lado institucional.
    describirEstadoInstitucional(enrutamiento, esSimulacro = false) {
        if (esSimulacro) return 'Simulacro: no se envía a ninguna institución.';
        const instituciones = (enrutamiento && enrutamiento.instituciones) || [];
        if (!instituciones.length) {
            return 'Ninguna institución con cobertura validada para esta ubicación. Si necesitas ayuda, llama a los números de emergencia.';
        }
        return `Visible en la bandeja de ${instituciones.join(', ')}. Aún nadie confirmó haberla recibido.`;
    },

    async ejecutarDespachoAlerta(tipoEmergencia, nivelGravedad, extra = {}) {
        const ubicacion = await new Promise((resolve) => {
            this.obtenerUbicacionReal(resolve, 'SOS activo: obteniendo ubicación actual...');
        });
        const lat = ubicacion.lat;
        const lng = ubicacion.lng;
        if (lat !== null && lng !== null) this.renderNumerosCercanos(lat, lng);
        // Un simulacro no toma foto ni envía correo.
        if (extra.es_simulacro !== true) {
            this.evidenciaAutomatica('SOS', { ubicacion: lat === null || lng === null ? null : { lat, lng } });
        }

        document.getElementById('coords-ciudadano').innerText = lat === null || lng === null
            ? 'Ubicación no disponible'
            : `Lat: ${lat.toFixed(4)}, Lng: ${lng.toFixed(4)}`;
        
        // Actualizar radar a Modo Emergencia Revelada
        const radarBadge = document.getElementById('radar-badge');
        radarBadge.innerText = "🚨 Ubicación Revelada (Emergencia Activa)";
        radarBadge.className = "text-[10px] font-semibold bg-red-950 text-red-400 border border-red-800 px-2.5 py-1 rounded-lg animate-pulse";

        this.agregarLogCiudadano(`Despachando ${tipoEmergencia} (Gravedad: ${nivelGravedad}) hacia PostGIS...`);

        try {
            const data = await ApiService.despacharAlerta({
                client_alert_id: await ApiService.obtenerClientAlertId(),
                usuario: this.usuarioActual,
                dispositivo_id: this.usuarioActual,
                tipo_emergencia: tipoEmergencia,
                nivel_gravedad: nivelGravedad,
                latitud: lat,
                longitud: lng,
                timestamp_dispositivo: new Date().toISOString(),
                ...extra
            });

            const estadoInstitucional = this.describirEstadoInstitucional(data.enrutamiento_institucional, extra.es_simulacro === true);
            this.actualizarBloqueoCorreoSeguridad();  // una alerta real fija el correo de seguridad
            const hayFamiliares = data.notificacion_familiar && data.notificacion_familiar.estado === 'DISPONIBLE_EN_BUZON';
            this.agregarLogCiudadano(`Alerta #${Number(data.alerta_id)} guardada en el servidor. Estado: ${this.escaparHtml(data.estado)}.`);
            this.agregarLogCiudadano(this.escaparHtml(estadoInstitucional));
            this.agregarLogCiudadano(hayFamiliares
                ? 'Disponible en el buzón de tus familiares vinculados. No hay confirmación de lectura.'
                : 'No tienes familiares vinculados que la reciban.');

            // Mostrar transmisión satelital a familiares con enlaces GPS
            const cajaFamiliar = document.getElementById('caja-alerta-familiar');
            const detalleFamiliar = document.getElementById('detalle-familiares-sos');
            const btnWa = document.getElementById('btn-compartir-wa');

            if (cajaFamiliar && detalleFamiliar) {
                cajaFamiliar.classList.remove('hidden');
                if (data.notificacion_familiar && data.notificacion_familiar.detalles && data.notificacion_familiar.detalles.length > 0) {
                    detalleFamiliar.innerHTML = data.notificacion_familiar.detalles.map(d => `
                        <div class="flex justify-between items-center py-1 border-b border-slate-800 last:border-0">
                            <div>
                                <span class="font-bold text-white">${d.nombre} (${d.parentesco})</span>
                                <span class="block text-[10px] text-emerald-400">✓ Ubicación GPS enviada</span>
                            </div>
                            <a href="${d.enlace_ubicacion}" target="_blank" class="text-blue-400 hover:text-blue-300 text-[10px] underline font-semibold">
                                📍 Abrir Mapa
                            </a>
                        </div>
                    `).join('');
                } else {
                    detalleFamiliar.innerHTML = `
                        <div class="text-amber-400 text-[10px]">
                            ${hayFamiliares ? 'Disponible en el buzón de tus familiares vinculados.' : '⚠️ No tienes familiares vinculados que la reciban.'}
                        </div>
                        <div class="text-slate-300 text-[10px]">${this.escaparHtml(estadoInstitucional)}</div>
                    `;
                }

                if (btnWa && data.notificacion_familiar && data.notificacion_familiar.enlace_compartir_whatsapp) {
                    btnWa.href = data.notificacion_familiar.enlace_compartir_whatsapp;
                }
            }

            // Actualizar Marcador en el Mapa
            if (this.mapaCiudadano && lat !== null && lng !== null) {
                if (this.marcadorCiudadano) this.mapaCiudadano.removeLayer(this.marcadorCiudadano);
                this.marcadorCiudadano = L.marker([lat, lng])
                    .addTo(this.mapaCiudadano)
                    .bindPopup(`<b>${extra.es_simulacro === true ? 'Simulacro registrado' : '🚨 SOS EN CURSO'}</b><br>ID: #${Number(data.alerta_id)}<br>${this.escaparHtml(tipoEmergencia)}`)
                    .openPopup();
                this.mapaCiudadano.setView([lat, lng], 15);
            }
        } catch (err) {
            if (err.alertaLocalGuardada) {
                this.agregarLogCiudadano('Sin confirmación del servidor. SOS guardado en este dispositivo y pendiente de reintento; usa los teléfonos oficiales visibles arriba si necesitas respuesta inmediata.');
            } else {
                this.agregarLogCiudadano(`❌ No se pudo guardar la alerta SOS: ${err.message}`);
            }
        }
    },

    agregarLogCiudadano(mensaje) {
        const log = document.getElementById('log-ciudadano');
        if (!log) return;
        const hora = new Date().toLocaleTimeString();
        log.innerHTML += `<div><span class="text-slate-500">[${hora}]</span> ${mensaje}</div>`;
        log.scrollTop = log.scrollHeight;
    },

    // ==========================================
    // SECCIÓN B2G: COMANDO INSTITUCIONAL & RUTAS
    // ==========================================
    configurarVistaB2G() {
        document.getElementById('vista-institucion').classList.remove('hidden');
        document.getElementById('vista-ciudadano').classList.add('hidden');

        this.inicializarMapaB2G();
        this.cargarAlertasB2G();
    },

    inicializarMapaB2G() {
        if (!this.mapaB2G) {
            setTimeout(() => {
                const { lat, lng } = CONFIG.DEFAULT_COORDS;
                this.mapaB2G = L.map('mapa-b2g').setView([lat, lng], 13);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    maxZoom: 19,
                    attribution: '© OpenStreetMap - QuantumGeoRescue B2G'
                }).addTo(this.mapaB2G);
            }, 300);
        } else {
            setTimeout(() => this.mapaB2G.invalidateSize(), 300);
        }
    },

    ACCIONES_ALERTA: {
        REGISTRADA: [['RECIBIDA', 'Confirmar recepción']],
        RECIBIDA: [['EN_ATENCION', 'Pasar a en atención'], ['RESUELTA', 'Marcar resuelta']],
        EN_ATENCION: [['ATENDIDA', 'Marcar atendida'], ['RESUELTA', 'Marcar resuelta']]
    },
    NOMBRES_ESTADO_ALERTA: {
        REGISTRADA: 'Sin confirmar', RECIBIDA: 'Recibida', EN_ATENCION: 'En atención',
        ATENDIDA: 'Atendida', RESUELTA: 'Resuelta', CANCELADA: 'Cancelada'
    },

    inicializarBandejaInstitucional() {
        if (this._bandejaHooked) return;
        this._bandejaHooked = true;
        document.getElementById('lista-alertas-b2g')?.addEventListener('click', async (event) => {
            const button = event.target.closest('[data-alert-state]');
            if (!button) return;
            const alertaId = Number(button.dataset.alertId);
            const estado = button.dataset.alertState;
            const cierra = estado === 'ATENDIDA' || estado === 'RESUELTA';
            if (cierra && !window.confirm(`¿Cerrar la alerta #${alertaId} como ${this.NOMBRES_ESTADO_ALERTA[estado].toLowerCase()}? Saldrá de la bandeja de abiertas.`)) return;
            button.disabled = true;
            try {
                await ApiService.cambiarEstadoAlerta(alertaId, estado);
                await this.cargarAlertasB2G();
            } catch (error) {
                button.disabled = false;
                alert(`No se pudo cambiar el estado: ${error.message}`);
            }
        });
    },

    async cargarAlertasB2G() {
        const contenedor = document.getElementById('lista-alertas-b2g');
        const contenedorAtendidos = document.getElementById('personas-atendidas-b2g');
        contenedor.innerHTML = `<div class="text-xs text-slate-400">Consultando PostGIS...</div>`;

        try {
            const alertas = await ApiService.obtenerAlertasActivas();
            this.alertasB2G = (alertas || []).map(a => ({ ...a, id: Number(a.id) }));

            document.getElementById('b2g-metrica-alertas').innerText = this.alertasB2G.length;

            if (!this.alertasB2G || this.alertasB2G.length === 0) {
                contenedor.innerHTML = `<div class="text-xs text-slate-500 italic p-3 bg-slate-950 rounded-xl border border-slate-800">No hay alertas abiertas asignadas a esta institución. Solo llegan las que caen dentro de la cobertura que validó la plataforma.</div>`;
                contenedorAtendidos.innerHTML = `<p class="text-xs text-slate-500">No hay personas atendidas aún.</p>`;
                document.getElementById('contador-personas-atendidas').innerText = '0';
                return;
            }

            const atendidos = this.alertasB2G.filter(a => a.estado === 'ATENDIDA');
            const activos = this.alertasB2G.filter(a => a.estado !== 'ATENDIDA');

            const personasAtendidas = [...new Map(atendidos.map(a => {
                const nombreUsuario = (a.usuario || a.dispositivo_id || 'Usuario no identificado');
                return [String(nombreUsuario).toLowerCase(), {
                    nombre: nombreUsuario,
                    total: 1,
                    alertas: [a.id]
                }];
            })).values()];

            document.getElementById('contador-personas-atendidas').innerText = String(personasAtendidas.length);
            contenedorAtendidos.innerHTML = personasAtendidas.length
                ? personasAtendidas.map(item => `
                    <div class="bg-emerald-950/40 border border-emerald-800 rounded-xl p-2 text-xs text-emerald-200">
                        <div class="font-bold">${this.escaparTexto(item.nombre)}</div>
                        <div class="text-[10px] text-emerald-300/80">Incidentes: ${item.alertas.length}</div>
                    </div>
                `).join('')
                : '<p class="text-xs text-slate-500">No hay personas atendidas aún.</p>';

            if (this.mapaB2G) {
                this.marcadoresB2G.forEach(m => this.mapaB2G.removeLayer(m));
            }
            this.marcadoresB2G = [];

            const renderCard = (a) => {
                const esCoaccion = a.tipo_emergencia === 'ROBO_ASALTO_COACCION';
                const atendida = a.estado === 'ATENDIDA';
                const estiloEstado = atendida ? 'bg-emerald-950 text-emerald-300 border-emerald-800' : esCoaccion ? 'bg-violet-950 text-violet-300 border-violet-800' : 'bg-red-950 text-red-400 border-red-800';
                // Tipo y usuario vienen de la app del ciudadano: se escapan antes de mostrarlos.
                const tipo = this.escaparTexto(a.tipo_emergencia);
                const usuario = this.escaparTexto(a.usuario || a.dispositivo_id);
                const estado = this.escaparTexto(this.NOMBRES_ESTADO_ALERTA[a.estado] || a.estado);
                const confirmacion = this.escaparTexto(a.estado_confirmacion);
                const tieneUbicacion = Number.isFinite(a.latitud) && Number.isFinite(a.longitud);
                const calidadUbicacion = tieneUbicacion && a.precision_m !== null && a.precision_m !== undefined
                    ? ` (±${Number(a.precision_m)} m${a.edad_lectura_s ? `, lectura de hace ${Number(a.edad_lectura_s)} s` : ''})`
                    : '';
                const acciones = (this.ACCIONES_ALERTA[a.estado] || []).map(([siguiente, etiqueta]) => `
                    <button type="button" data-alert-id="${a.id}" data-alert-state="${siguiente}" class="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1.5 text-[10px] font-semibold text-white hover:bg-slate-700">${etiqueta}</button>
                `).join('');

                if (this.mapaB2G && tieneUbicacion) {
                    const color = atendida ? '#10b981' : esCoaccion ? '#a855f7' : '#ef4444';
                    const m = L.marker([a.latitud, a.longitud], {
                        icon: L.divIcon({
                            html: `<div style="background:${color};border:2px solid white;border-radius:999px;width:14px;height:14px;box-shadow:0 0 12px ${color};"></div>`,
                            className: '',
                            iconSize: [14, 14]
                        })
                    }).addTo(this.mapaB2G)
                        .bindPopup(`
                            <b>${esCoaccion ? '🚨' : '⚠️'} Alerta #${a.id}</b><br>
                            Tipo: ${tipo}<br>
                            Usuario: ${usuario}<br>
                            Gravedad: ${Number(a.nivel_gravedad)}/5<br>
                            Estado: ${estado}<br>
                            Confirmación: ${confirmacion}
                        `);
                    this.marcadoresB2G.push(m);
                }

                return `
                    <article class="bg-slate-950 border ${atendida ? 'border-emerald-700/80 opacity-80' : esCoaccion ? 'border-violet-700/80' : 'border-slate-800/80'} p-3 rounded-xl text-xs transition">
                        <div class="flex items-start justify-between gap-2">
                            <div class="min-w-0">
                                <div class="flex items-center gap-2">
                                    <span class="w-2 h-2 rounded-full ${atendida ? 'bg-emerald-500' : 'bg-amber-400'} flex-shrink-0" aria-hidden="true"></span>
                                    <span class="font-bold ${esCoaccion ? 'text-violet-400' : 'text-red-400'} truncate">#${a.id} • ${tipo}</span>
                                </div>
                                <div class="mt-1 text-slate-400 text-[10px]">Usuario: <span class="text-slate-200">${usuario}</span> · Canal: <span class="text-slate-200">${this.escaparTexto(a.canal_entrada || 'API')}</span></div>
                            </div>
                            <span class="${estiloEstado} px-2 py-0.5 rounded text-[10px] border whitespace-nowrap">${estado}</span>
                        </div>

                        <div class="mt-2 flex items-center justify-between gap-2 text-[10px] text-slate-400">
                            <span>Coordenadas: ${tieneUbicacion ? `${a.latitud.toFixed(4)}, ${a.longitud.toFixed(4)}${calidadUbicacion}` : 'No proporcionadas'}</span>
                            <span class="${esCoaccion ? 'text-violet-400' : 'text-amber-400'}">${esCoaccion ? 'Coacción' : 'Gravedad: ' + Number(a.nivel_gravedad)}</span>
                        </div>

                        <div class="mt-2 flex items-center justify-between gap-2 text-[10px] text-slate-500">
                            <span>Confirmación del usuario: <b class="text-slate-300">${confirmacion}</b></span>
                            <span>${this.escaparTexto(this.formatearFecha(a.creado_en))}</span>
                        </div>

                        ${acciones ? `<div class="mt-3 flex flex-wrap justify-end gap-2 border-t border-slate-800 pt-2">${acciones}</div>` : ''}
                    </article>
                `;
            };

            contenedor.innerHTML = `
                <div class="space-y-4">
                    <div class="space-y-2">
                        <div class="flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-400">
                            <span>Activos</span>
                            <span>${activos.length}</span>
                        </div>
                        ${activos.length
                            ? activos.map(renderCard).join('')
                            : '<div class="text-xs text-slate-500 italic p-3 bg-slate-950 rounded-xl border border-slate-800">Sin incidentes activos.</div>'}
                    </div>

                    <div class="border-t border-slate-800 pt-3 space-y-2">
                        <div class="flex items-center justify-between text-[10px] uppercase tracking-wider text-slate-400">
                            <span>Atendidos</span>
                            <span>${atendidos.length}</span>
                        </div>
                        ${atendidos.length
                            ? atendidos.map(renderCard).join('')
                            : '<div class="text-xs text-slate-500 italic p-3 bg-slate-950 rounded-xl border border-slate-800">No hay incidentes atendidos aún.</div>'}
                    </div>
                </div>
            `;

        } catch (err) {
            contenedor.innerHTML = `<div class="text-xs text-red-400">Error al consultar alertas: ${this.escaparTexto(err.message)}</div>`;
        }
    },

    async calcularRutaRescateB2G(destLat, destLng, alertaId) {
        document.getElementById('ruta-estado').innerText =
            `No se puede calcular una ruta para la alerta #${alertaId}: proveedor no configurado.`;
        document.getElementById('ruta-tiempo').innerText = 'ETA no disponible';
    }
};

document.addEventListener("DOMContentLoaded", () => {
    App.init();
});