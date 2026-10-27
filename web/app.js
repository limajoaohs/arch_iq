// Arquitetura em Nuvem - ArchIQ Web Interface
// Interação com a API FastAPI para análise de arquitetura
// Endpoint: POST /api/audit (JSON com code_or_prompt e session_id opcional)

document.addEventListener('DOMContentLoaded', function() {
  initElements();
  initEventListeners();
  updateAnalyzeButton();
});

/* Elementos do DOM */
const elements = {
  uploadArea: document.querySelector('.upload-area'),
  fileInput: document.querySelector('input[type="file"]'),
  analyzeBtn: document.querySelector('.btn-analyze'),
  loadingOverlay: document.querySelector('.loading-overlay'),
  resultsSection: document.querySelector('.results-section'),
  scoreElement: document.querySelector('.score-value'),
  descElement: document.querySelector('.score-desc'),
  findingsList: document.querySelector('.findings-list'),
  optimizationsList: document.querySelector('.optimizations-list'),
  mermaidDiv: document.querySelector('.mermaid'),
  reportSection: document.querySelector('.report-section'),
  reportContent: document.querySelector('#reportContent'),
  reportHint: document.querySelector('#reportHint'),
  btnToggleTechnical: document.querySelector('#btnToggleTechnical'),
  reportContentTechnical: document.querySelector('#reportContentTechnical'),
  downloadBtn: document.querySelector('.btn-download'),
  fileNameDisplay: document.querySelector('.file-name'),
  errorMessage: document.getElementById('errorMessage'),
};

/* Estado da aplicação */
const state = {
  terraformCode: null,   // Código lido do arquivo ou digitado no editor
  fileName: null,        // Nome do arquivo (se houver)
  isAnalyzing: false,    // Previne envios duplicados
  MAX_FILE_SIZE: 500 * 1024, // 500 KB
  ALLOWED_EXTENSIONS: ['.tf', '.json', '.tf.json'],
};

/* ========================================================================
   Inicialização
   ======================================================================== */

function initElements() {
  if (!elements.analyzeBtn) {
    console.error('Botão de análise não encontrado');
    return;
  }
}

function initEventListeners() {
  // Clique na área de upload abre o seletor de arquivo
  if (elements.uploadArea && elements.fileInput) {
    elements.uploadArea.addEventListener('click', function(e) {
      if (e.target !== elements.analyzeBtn && !elements.analyzeBtn.contains(e.target)) {
        elements.fileInput.click();
      }
    });
  }

  // Seleção de arquivo
  if (elements.fileInput) {
    elements.fileInput.addEventListener('change', handleFileSelect);
  }

  // Botão de análise
  if (elements.analyzeBtn) {
    elements.analyzeBtn.addEventListener('click', handleAnalyze);
  }

  // Botão de download
  if (elements.downloadBtn) {
    elements.downloadBtn.addEventListener('click', handleDownload);
  }

  // Editor de código (textarea se existir)
  const textarea = document.querySelector('textarea');
  if (textarea) {
    textarea.addEventListener('input', function() {
      const val = textarea.value.trim();
      state.terraformCode = val || null;
      if (state.terraformCode) {
        state.fileName = null;
        if (elements.fileInput) elements.fileInput.value = '';
        if (elements.fileNameDisplay) {
          elements.fileNameDisplay.textContent = 'Código colado no editor';
          elements.fileNameDisplay.className = 'file-name valid';
        }
      }
      updateAnalyzeButton();
    });
  }

  // Drag & drop na área de upload
  if (elements.uploadArea) {
    elements.uploadArea.addEventListener('dragover', handleDragOver);
    elements.uploadArea.addEventListener('dragleave', handleDragLeave);
    elements.uploadArea.addEventListener('drop', handleDrop);
  }
}

/* ========================================================================
   Manipulação de arquivo (upload)
   ======================================================================== */

function handleFileSelect(event) {
  const file = event.target.files[0];
  if (!file) return;

  clearError();

  // Validar extensão
  const fileNameLower = file.name.toLowerCase();
  const hasValidExtension = state.ALLOWED_EXTENSIONS.some(ext =>
    fileNameLower.endsWith(ext)
  );
  if (!hasValidExtension) {
    showError('Por favor, envie apenas arquivos .tf, .json ou .tf.json.');
    elements.fileInput.value = '';
    resetFileDisplay();
    state.terraformCode = null;
    state.fileName = null;
    updateAnalyzeButton();
    return;
  }

  // Validar tamanho
  if (file.size > state.MAX_FILE_SIZE) {
    showError('O arquivo é muito grande (limite: 500 KB).');
    elements.fileInput.value = '';
    resetFileDisplay();
    state.terraformCode = null;
    state.fileName = null;
    updateAnalyzeButton();
    return;
  }

  // Ler arquivo como texto
  const reader = new FileReader();
  reader.onload = function(e) {
    const code = e.target.result;
    if (!code || !code.trim()) {
      showError('O arquivo selecionado está vazio.');
      elements.fileInput.value = '';
      resetFileDisplay();
      state.terraformCode = null;
      state.fileName = null;
      updateAnalyzeButton();
      return;
    }
    state.terraformCode = code.trim();
    state.fileName = file.name;
    if (elements.fileNameDisplay) {
      elements.fileNameDisplay.textContent = `✓ ${file.name}`;
      elements.fileNameDisplay.className = 'file-name valid';
    }
    updateAnalyzeButton();
  };
  reader.onerror = function() {
    showError('Não foi possível ler o arquivo selecionado.');
    elements.fileInput.value = '';
    resetFileDisplay();
    state.terraformCode = null;
    state.fileName = null;
    updateAnalyzeButton();
  };
  reader.readAsText(file);
}

/* Drag & drop */
function handleDragOver(e) {
  e.preventDefault();
  if (elements.uploadArea) elements.uploadArea.classList.add('dragover');
}

function handleDragLeave(e) {
  e.preventDefault();
  if (elements.uploadArea) elements.uploadArea.classList.remove('dragover');
}

function handleDrop(e) {
  e.preventDefault();
  if (elements.uploadArea) elements.uploadArea.classList.remove('dragover');

  const files = e.dataTransfer.files;
  if (!files || files.length === 0) return;

  readDroppedFile(files[0]);
}

function readDroppedFile(file) {
  clearError();
  const fileNameLower = file.name.toLowerCase();
  const hasValidExtension = state.ALLOWED_EXTENSIONS.some(ext =>
    fileNameLower.endsWith(ext)
  );
  if (!hasValidExtension) {
    showError('Por favor, envie apenas arquivos .tf, .json ou .tf.json.');
    state.terraformCode = null;
    state.fileName = null;
    updateAnalyzeButton();
    return;
  }
  if (file.size > state.MAX_FILE_SIZE) {
    showError('O arquivo é muito grande (limite: 500 KB).');
    state.terraformCode = null;
    state.fileName = null;
    updateAnalyzeButton();
    return;
  }
  const reader = new FileReader();
  reader.onload = function(e) {
    const code = e.target.result;
    if (!code || !code.trim()) {
      showError('O arquivo selecionado está vazio.');
      state.terraformCode = null;
      state.fileName = null;
      updateAnalyzeButton();
      return;
    }
    state.terraformCode = code.trim();
    state.fileName = file.name;
    if (elements.fileNameDisplay) {
      elements.fileNameDisplay.textContent = `✓ ${file.name}`;
      elements.fileNameDisplay.className = 'file-name valid';
    }
    if (elements.fileInput) elements.fileInput.value = '';
    updateAnalyzeButton();
  };
  reader.onerror = function() {
    showError('Não foi possível ler o arquivo solto.');
    state.terraformCode = null;
    state.fileName = null;
    updateAnalyzeButton();
  };
  reader.readAsText(file);
}

function resetFileDisplay() {
  if (elements.fileNameDisplay) {
    elements.fileNameDisplay.textContent = 'Nenhum arquivo selecionado';
    elements.fileNameDisplay.className = 'file-name';
  }
}

/* ========================================================================
   Controle do botão de análise
   ======================================================================== */

function updateAnalyzeButton() {
  const hasInput = !!state.terraformCode;
  const canAnalyze = hasInput && !state.isAnalyzing;
  if (elements.analyzeBtn) {
    elements.analyzeBtn.disabled = !canAnalyze;
    elements.analyzeBtn.setAttribute('aria-disabled', !canAnalyze);
  }
}

/* ========================================================================
   Handler principal de análise (POST /api/audit)
   ======================================================================== */

async function handleAnalyze() {
  if (state.isAnalyzing) return;

  // Obter código do editor se não houver do arquivo
  let code = state.terraformCode;
  if (!code) {
    const textarea = document.querySelector('textarea');
    if (textarea) {
      code = textarea.value.trim();
      state.terraformCode = code || null;
    }
  }

  // Validação de entrada
  if (!code) {
    showError('Por favor, envie um arquivo Terraform ou cole seu código no editor.');
    return;
  }

  clearResults();
  clearError();
  showLoading(true);
  state.isAnalyzing = true;
  updateAnalyzeButton();

  try {
    // Enviar para a API via POST com JSON (não definir Content-Type com boundary fixo)
    const apiUrl = (window.API_CONFIG?.baseUrl || '') + (window.API_CONFIG?.auditEndpoint || '/api/audit');
    const response = await fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify({ code_or_prompt: code }),
    });

    if (!response.ok) {
      let errorDetail = 'Erro na análise';
      try {
        const errorData = await response.json();
        errorDetail = errorData.detail || errorData.message || errorDetail;
      } catch (_) {
        try {
          const text = await response.text();
          if (text) errorDetail = text;
        } catch (__) {}
      }
      throw new Error(errorDetail);
    }

    const result = await response.json();
    displayResults(result);

  } catch (error) {
    console.error('Erro na análise:', error);
    showError(`Erro ao analisar arquitetura: ${error.message || 'Erro desconhecido'}`);
  } finally {
    showLoading(false);
    state.isAnalyzing = false;
    updateAnalyzeButton();
  }
}

/* ========================================================================
   Utilitários de UI
   ======================================================================== */

function showLoading(show) {
  if (elements.loadingOverlay) {
    if (show) {
      elements.loadingOverlay.style.display = 'flex';
      elements.loadingOverlay.setAttribute('aria-hidden', 'false');
    } else {
      elements.loadingOverlay.style.display = 'none';
      elements.loadingOverlay.setAttribute('aria-hidden', 'true');
    }
  }
}

function showError(message) {
  if (elements.errorMessage) {
    elements.errorMessage.textContent = message;
    elements.errorMessage.classList.add('visible');
    elements.errorMessage.setAttribute('role', 'alert');
    elements.errorMessage.focus({ preventScroll: true });
  }
}

function clearError() {
  if (elements.errorMessage) {
    elements.errorMessage.textContent = '';
    elements.errorMessage.classList.remove('visible');
    elements.errorMessage.removeAttribute('role');
  }
}

function clearResults() {
  if (elements.scoreElement) elements.scoreElement.textContent = '0';
  if (elements.descElement) elements.descElement.textContent = '';
  if (elements.findingsList) elements.findingsList.innerHTML = '';
  if (elements.optimizationsList) elements.optimizationsList.innerHTML = '';
  if (elements.mermaidDiv) elements.mermaidDiv.innerHTML = '';
  if (elements.reportSection) {
    elements.reportSection.style.display = 'none';
    if (elements.reportContent) elements.reportContent.textContent = '';
    if (elements.reportContentTechnical) elements.reportContentTechnical.textContent = '';
    if (elements.reportHint) elements.reportHint.textContent = '';
    if (elements.btnToggleTechnical) elements.btnToggleTechnical.style.display = 'inline-block';
    if (elements.reportContentTechnical) elements.reportContentTechnical.style.display = 'none';
  }
  if (elements.downloadBtn) {
    elements.downloadBtn.style.display = 'none';
    elements.downloadBtn.removeAttribute('href');
  }
  if (elements.resultsSection) {
    elements.resultsSection.style.display = 'none';
  }
}

/* ========================================================================
   Exibição de resultados
   ======================================================================== */

function displayResults(result) {
  // Score
  if (elements.scoreElement) {
    const score = result.score ?? 0;
    elements.scoreElement.textContent = score;

    let badgeClass = 'atencao';
    let badgeText = getStatusText(score);
    if (score >= 85) badgeClass = 'alto';
    else if (score >= 65) badgeClass = 'medio-alto';
    else if (score >= 35) badgeClass = 'medio-baixo';
    else badgeClass = 'baixo';

    const existingBadge = elements.scoreElement.parentElement?.querySelector('.badge');
    if (existingBadge) existingBadge.remove();

    const badge = document.createElement('span');
    badge.className = `badge ${badgeClass}`;
    badge.textContent = badgeText;
    if (elements.scoreElement.parentElement) {
      elements.scoreElement.parentElement.appendChild(badge);
    }
  }

  // Descrição / poupança
  if (elements.descElement) {
    const savings = result.finops_audit?.monthly_savings_pct ?? 0;
    elements.descElement.textContent = `Poupança mensal potencial: ${savings}%`;
  }

  // Findings de segurança
  if (elements.findingsList && result.security_audit) {
    const findings = result.security_audit.findings || [];
    elements.findingsList.innerHTML = '';
    if (findings.length === 0) {
      elements.findingsList.innerHTML = '<p style="color:#64748b; font-size:0.9rem;">Nenhum finding de segurança detectado.</p>';
    } else {
      findings.forEach(finding => {
        const findingEl = document.createElement('div');
        const severity = (finding.severity || 'low').toLowerCase();
        findingEl.className = `finding ${severity}`;
        findingEl.innerHTML = `
          <span class="severity">[${finding.severity}]</span>
          ${escapeHtml(finding.service || 'Terraform')}: ${escapeHtml(finding.rule || '')}
        `;
        elements.findingsList.appendChild(findingEl);
      });
    }
  }

  // Otimizações FinOps
  if (elements.optimizationsList && result.finops_audit) {
    const optimizations = result.finops_audit.optimizations || [];
    elements.optimizationsList.innerHTML = '';
    if (optimizations.length === 0) {
      elements.optimizationsList.innerHTML = '<p style="color:#64748b; font-size:0.9rem;">Nenhuma otimização de custo identificada.</p>';
    } else {
      optimizations.forEach(opt => {
        const optEl = document.createElement('div');
        optEl.className = 'optimization';
        optEl.innerHTML = `<span class="service">${escapeHtml(opt.service || 'Geral')}</span>: ${escapeHtml(opt.action || '')} (${escapeHtml(opt.impact || '')})`;
        elements.optimizationsList.appendChild(optEl);
      });
    }
  }

  // Diagrama Mermaid
  if (elements.mermaidDiv && result.final_report) {
    const mermaidMatch = result.final_report.match(/graph TD[\s\S]*?\n```/m);
    const mermaidCode = mermaidMatch ? mermaidMatch[0].replace('\n```', '') : 'graph TD\n    SERVICE[Service]';
    elements.mermaidDiv.innerHTML = `<pre class="code-block">${escapeHtml(mermaidCode)}</pre>`;
  }

  // Relatório completo: mostra primeiro a explicacao didatica para leigos
  if (elements.reportSection && elements.reportContent) {
    elements.reportSection.style.display = 'block';
    const layperson = result.layperson_explanation || result.final_report || '';
    const technical = result.technical_report || '';
    elements.reportContent.textContent = layperson;
    if (elements.reportHint) {
      elements.reportHint.textContent = layperson
        ? 'Explicacao gerada por IA (Amazon Bedrock) em linguagem simples para quem nao entende de tecnologia da nuvem.'
        : '';
    }
    if (elements.btnToggleTechnical) {
      elements.btnToggleTechnical.style.display = technical ? 'inline-block' : 'none';
      elements.btnToggleTechnical.onclick = function() {
        const isHidden = elements.reportContentTechnical.style.display === 'none';
        elements.reportContentTechnical.style.display = isHidden ? 'block' : 'none';
        elements.btnToggleTechnical.textContent = isHidden
          ? 'Ocultar relatorio tecnico detalhado'
          : 'Ver relatorio tecnico detalhado';
      };
    }
    if (elements.reportContentTechnical) {
      elements.reportContentTechnical.textContent = technical;
      elements.reportContentTechnical.style.display = 'none';
    }
  }

  // Botão download
  if (elements.downloadBtn) {
    const reportLocation = result.report_location;
    elements.downloadBtn.style.display = 'inline-block';
    elements.downloadBtn.onclick = function(e) {
      e.preventDefault();
      if (reportLocation) {
        window.open(reportLocation, '_blank');
      } else if (result.final_report) {
        const blob = new Blob([result.final_report], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'archiq-relatorio.md';
        a.click();
        URL.revokeObjectURL(url);
      }
    };
  }

  // Mostrar seção de resultados
  if (elements.resultsSection) {
    elements.resultsSection.style.display = 'block';
    elements.resultsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

/* Helper: texto do status */
function getStatusText(score) {
  if (score >= 85) return 'ALTO';
  if (score >= 65) return 'MEDIO-ALTO';
  if (score >= 35) return 'MEDIO-BAIXO';
  return 'BAIXO';
}

/* Escape HTML */
function escapeHtml(text) {
  if (text == null) return '';
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

/* Download do relatório */
function handleDownload(e) {
  e.preventDefault();
  if (elements.downloadBtn) {
    const reportLocation = elements.downloadBtn.getAttribute('href');
    if (reportLocation) {
      window.open(reportLocation, '_blank');
    }
  }
}
