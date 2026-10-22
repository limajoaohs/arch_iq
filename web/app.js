// Arquitetura em Nuvem - ArchIQ Web Interface
// Interação com a API FastAPI para análise de arquitetura

document.addEventListener('DOMContentLoaded', function() {
  initElements();
  initEventListeners();
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
  downloadBtn: document.querySelector('.btn-download'),
  fileNameDisplay: document.querySelector('.file-name')
};

/* Inicializar elementos */
function initElements() {
  // Verificar se elementos existem
  if (!elements.analyzeBtn) {
    console.error('Botão de análise não encontrado');
    return;
  }
}

/* Event Listeners */
function initEventListeners() {
  // Upload click
  if (elements.uploadArea) {
    elements.uploadArea.addEventListener('click', function() {
      if (elements.fileInput) {
        elements.fileInput.click();
      }
    });
  }

  // File input change
  if (elements.fileInput) {
    elements.fileInput.addEventListener('change', handleFileSelect);
  }

  // Analyze button
  if (elements.analyzeBtn) {
    elements.analyzeBtn.addEventListener('click', handleAnalyze);
  }

  // Download button
  if (elements.downloadBtn) {
    elements.downloadBtn.addEventListener('click', handleDownload);
  }
}

/* Lidar com seleção de arquivo */
function handleFileSelect(event) {
  const file = event.target.files[0];
  if (file) {
    elements.fileNameDisplay.textContent = file.name;
    
    // Verificar extensão
    const allowedExtensions = ['.tf', '.json', '.tf.json'];
    const ext = file.name.substring(file.name.lastIndexOf('.'));
    
    if (!allowedExtensions.includes(ext.toLowerCase())) {
      alert('Por favor, envie arquivos .tf ou .json');
      elements.fileInput.value = '';
      elements.fileNameDisplay.textContent = 'Nenhum arquivo selecionado';
      return;
    }
    
    // Ler arquivo como texto
    const reader = new FileReader();
    reader.onload = function(e) {
      elements.uploadArea.dataset.code = e.target.result;
      elements.fileNameDisplay.textContent = `✓ ${file.name}`;
    };
    reader.readAsText(file);
  }
}

/* Handler principal de análise */
async function handleAnalyze() {
  // Obter código da arquitetura
  let code = elements.uploadArea ? elements.uploadArea.dataset.code : null;
  
  // Se não houver código do upload, tentar do textarea se existir
  if (!code) {
    const textarea = document.querySelector('textarea');
    if (textarea) {
      code = textarea.value;
    }
  }
  
  // Se ainda assim não tiver código, mostrar aviso
  if (!code) {
    alert('Por favor, envie um arquivo Terraform ou cole seu código abaixo.');
    return;
  }
  
  // Limpar resultados anteriores
  clearResults();
  
  // Mostrar loading
  showLoading(true);
  
  try {
    // Enviar para a API
    const response = await fetch('/api/audit', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ code_or_prompt: code })
    });
    
    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'Erro na análise');
    }
    
    const result = await response.json();
    displayResults(result);
    
  } catch (error) {
    console.error('Erro na análise:', error);
    alert(`Erro ao analisar arquitetura: ${error.message}`);
  } finally {
    showLoading(false);
  }
}

/* Limpar resultados anteriores */
function clearResults() {
  if (elements.scoreElement) elements.scoreElement.textContent = '0';
  if (elements.descElement) elements.descElement.textContent = '';
  if (elements.findingsList) elements.findingsList.innerHTML = '';
  if (elements.optimizationsList) elements.optimizationsList.innerHTML = '';
  if (elements.mermaidDiv) elements.mermaidDiv.innerHTML = '';
  if (elements.reportSection) {
    elements.reportSection.style.display = 'none';
    elements.reportSection.innerHTML = '';
  }
  if (elements.downloadBtn) elements.downloadBtn.style.display = 'none';
  elements.fileNameDisplay.textContent = 'Nenhum arquivo selecionado';
}

/* Exibir resultados na tela */
function displayResults(result) {
  // Score e status
  if (elements.scoreElement) {
    const score = result.score || 0;
    elements.scoreElement.textContent = score;
    
    // Atualizar badge de status
    const badge = document.querySelector('.score-badge');
    if (badge) badge.remove();
    
    let badgeClass = 'atencao';
    if (score >= 90) badgeClass = 'excelente';
    else if (score >= 75) badgeClass = 'boa';
    else if (score >= 50) badgeClass = 'regular';
    
    if (elements.scoreElement.parentElement) {
      const badge = document.createElement('span');
      badge.className = `badge ${badgeClass}`;
      badge.textContent = getStatusText(score);
      elements.scoreElement.parentElement.appendChild(badge);
    }
  }
  
  if (elements.descElement) {
    const savings = result.finops_audit?.monthly_savings_pct || 0;
    elements.descElement.textContent = `Poupança mensal potencial: ${savings}%`;
  }
  
  // Findings
  if (elements.findingsList && result.security_audit) {
    const findings = result.security_audit.findings || [];
    elements.findingsList.innerHTML = '';
    
    findings.forEach(finding => {
      const findingEl = document.createElement('div');
      findingEl.className = `finding ${finding.severity.toLowerCase()}`;
      findingEl.innerHTML = `
        <span class="severity">[${finding.severity}]</span>
        ${finding.service}: ${finding.rule}
      `;
      elements.findingsList.appendChild(findingEl);
    });
  }
  
  // Otimizações FinOps
  if (elements.optimizationsList && result.finops_audit) {
    const optimizations = result.finops_audit.optimizations || [];
    elements.optimizationsList.innerHTML = '';
    
    optimizations.forEach(opt => {
      const optEl = document.createElement('div');
      optEl.className = 'optimization';
      optEl.innerHTML = `<span class="service">${opt.service}</span>: ${opt.action} (${opt.impact})`;
      elements.optimizationsList.appendChild(optEl);
    });
  }
  
  // Diagrama Mermaid
  if (elements.mermaidDiv && result.final_report) {
    const mermaidMatch = result.final_report.match(/graph TD[\s\S]*?^/m);
    const mermaidCode = mermaidMatch ? mermaidMatch[0] : 'graph TD\n    SERVICE[Service]';
    elements.mermaidDiv.innerHTML = `<pre class="code-block">${mermaidCode}</pre>`;
  }
  
  // Relatório completo
  if (elements.reportSection) {
    elements.reportSection.style.display = 'block';
    
    // Extrair o relatório markdown principal
    let reportContent = result.final_report || '';
    // Remover o diagrama mermaid do início para não duplicar
    if (reportContent.includes('graph TD')) {
      const parts = reportContent.split('---');
      if (parts.length > 1) {
        reportContent = parts[parts.length - 1];
      }
    }
    
    elements.reportSection.innerHTML = `
      <pre class="code-block">${escapeHtml(reportContent)}</pre>
    `;
    elements.reportSection.style.display = 'block';
  }
  
  // Botão download
  if (elements.downloadBtn) {
    const reportLocation = result.report_location;
    elements.downloadBtn.style.display = 'inline-block';
    elements.downloadBtn.onclick = () => {
      if (reportLocation) {
        window.open(reportLocation, '_blank');
      } else {
        // Baixar o markdown como arquivo
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
  
  // Remover classe de loading do upload area
  if (elements.uploadArea) {
    elements.uploadArea.classList.remove('dragover');
  }
  
  // Mostrar seção de resultados
  if (elements.resultsSection) {
    elements.resultsSection.style.display = 'block';
  }
  
  // Esconder loading
  function showLoading(show) {
    // Este handler é definido inline, vamos apenas esconder
  }
}

/* Helper: obter texto do status */
function getStatusText(score) {
  if (score >= 90) return 'EXCELENTE';
  if (score >= 75) return 'BOA';
  if (score >= 50) return 'REGULAR';
  return 'ATENÇÃO';
}

/* Escape HTML */
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/* Show loading state */
function showLoading(show) {
  const loading = document.querySelector('.loading-overlay');
  if (loading) {
    loading.style.display = show ? 'flex' : 'none';
  }
}