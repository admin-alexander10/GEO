// Configuración global del cliente frontend QuantumGeoRescue AI
const CONFIG = {
    API_HOSTS: [
        "http://127.0.0.1:8001",
        "http://localhost:8001",
        "http://127.0.0.1:8000",
        "http://localhost:8000"
    ],
    API_PREFIX: "/api/v1",
    GEOAPIFY_KEY: "d055c0b4-9aad-4446-b964-ffb91a31c15a",
    DEFAULT_COORDS: {
        lat: -7.1637,
        lng: -78.5003,
        ciudad: "Cajamarca, Perú"
    },
    EMERGENCY_CONTACTS: [
        { label: "PNP", number: "105" },
        { label: "Bomberos", number: "116" },
        { label: "SAMU", number: "106" }
    ],
    STORAGE_KEYS: {
        USER: "qgeo_user",
        ROLE: "qgeo_rol",
        TOKEN: "qgeo_token",
        CODE: "qgeo_code",
        INSTITUTION: "qgeo_institution"
    }
};
