// ============================================================================
// Configuracao da API ArchIQ
// ============================================================================
// Altere 'baseUrl' para a URL do seu backend FastAPI em producao.
// Exemplos:
//   Desenvolvimento local: ''  (mesmo dominio)
//   Render/Railway:        'https://seu-backend.onrender.com'
//   Fly.io:                'https://seu-app.fly.dev'
//   AWS/API Gateway:       'https://abc123.execute-api.us-east-1.amazonaws.com'
window.API_CONFIG = {
  baseUrl: '',
  auditEndpoint: '/api/audit',
  healthEndpoint: '/health'
};
