// ============================================================================
// Configuracao da API ArchIQ
// ============================================================================
// IMPORTANTE: Em producao (GitHub Pages), preencha 'baseUrl' com a URL do seu
// backend FastAPI hospedado externamente (Render, Railway, Fly.io, etc.).
//
// Exemplos:
//   Desenvolvimento local: ''  (mesmo dominio, backend rodando em localhost)
//   Producao:              'https://seu-backend.onrender.com'
//                          'https://seu-app.railway.app'
//                          'https://seu-app.fly.dev'
window.API_CONFIG = {
  // URL do backend hospedado no Render
  baseUrl: 'https://arch-iq.onrender.com',
  auditEndpoint: '/api/audit',
  healthEndpoint: '/health'
};
