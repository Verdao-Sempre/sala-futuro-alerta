// Elementos do DOM
const form = document.getElementById('loginForm');
const raInput = document.getElementById('ra');
const digitoInput = document.getElementById('digito');
const senhaInput = document.getElementById('senha');
const submitBtn = document.getElementById('submitBtn');
const loadingDiv = document.getElementById('loading');
const alertDiv = document.getElementById('alert');
const resultsDiv = document.getElementById('results');
const resultsContainer = document.getElementById('resultsContainer');

// Event listeners
form.addEventListener('submit', handleSubmit);

// Validar inputs em tempo real
raInput.addEventListener('input', validateForm);
digitoInput.addEventListener('input', validateForm);
senhaInput.addEventListener('input', validateForm);

function validateForm() {
    const ra = raInput.value.trim();
    const digito = digitoInput.value.trim();
    const senha = senhaInput.value.trim();

    const isValid = ra.length > 0 && digito.length > 0 && senha.length > 0;
    submitBtn.disabled = !isValid;
}

async function handleSubmit(e) {
    e.preventDefault();
    
    const ra = raInput.value.trim();
    const digito = digitoInput.value.trim();
    const senha = senhaInput.value.trim();

    if (!ra || !digito || !senha) {
        showAlert('Por favor, preencha todos os campos', 'error');
        return;
    }

    // Limpar resultados anteriores
    resultsDiv.classList.remove('show');
    alertDiv.classList.remove('show');

    // Mostrar loading
    loadingDiv.classList.add('active');
    submitBtn.disabled = true;

    try {
        const response = await fetch('/api/processar', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                ra: ra,
                digito: digito,
                senha: senha
            })
        });

        const data = await response.json();

        if (response.ok) {
            showAlert(`✓ ${data.message}`, 'success');
            displayResults(data.atividades || []);
            // Limpar form após sucesso
            form.reset();
            validateForm();
        } else {
            showAlert(`✗ Erro: ${data.error}`, 'error');
        }
    } catch (error) {
        console.error('Erro:', error);
        showAlert(`✗ Erro na conexão: ${error.message}`, 'error');
    } finally {
        loadingDiv.classList.remove('active');
        submitBtn.disabled = false;
        validateForm();
    }
}

function showAlert(message, type) {
    alertDiv.textContent = message;
    alertDiv.className = `alert alert-${type} show`;
    
    // Auto-hide em 8 segundos
    setTimeout(() => {
        alertDiv.classList.remove('show');
    }, 8000);
}

function displayResults(atividades) {
    if (atividades.length === 0) {
        showAlert('Nenhuma atividade encontrada', 'info');
        return;
    }

    resultsContainer.innerHTML = '';

    atividades.forEach((atividade, index) => {
        const item = document.createElement('div');
        item.className = 'result-item';
        
        const statusClass = atividade.status === 'sucesso' ? 'status-success' : 
                           atividade.status === 'aviso' ? 'status-warning' : 'status-error';
        
        const statusText = atividade.status === 'sucesso' ? '✓ Respondida' :
                          atividade.status === 'aviso' ? '⚠️  Aviso' : '✗ Erro';

        item.innerHTML = `
            <h3>📚 ${atividade.nome}</h3>
            <p><strong>Questões respondidas:</strong> ${atividade.cliques || 0}</p>
            <p><strong>URL:</strong> <a href="${atividade.url}" target="_blank" style="color: #667eea; text-decoration: none;">Abrir atividade</a></p>
            ${atividade.descricao ? `<p><strong>Descrição:</strong> ${atividade.descricao}</p>` : ''}
            <span class="result-status ${statusClass}">${statusText}</span>
        `;

        resultsContainer.appendChild(item);
    });

    resultsDiv.classList.add('show');
}

// Validar ao carregar
document.addEventListener('DOMContentLoaded', () => {
    validateForm();
});
