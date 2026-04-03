// API key is read from URL parameter: ?key=xxx
// This way the demo URL itself is the "access token"
// Share: demo.html?key=YOUR_KEY — only people with the link can use it
var API_BASE = 'https://ekb-poc-api.azurewebsites.net/api';
var API_KEY = new URLSearchParams(window.location.search).get('key') || '';
function apiUrl(endpoint) {
  return API_BASE + '/' + endpoint + (API_KEY ? '?code=' + API_KEY : '');
}
var API_URL = apiUrl('query');

var SVG_ICONS = {
  pending: '<svg viewBox="0 0 24 24" fill="none" stroke="#9ca3af" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
  active: '<svg viewBox="0 0 24 24" fill="none" stroke="#d97706" stroke-width="2"><circle cx="12" cy="12" r="10" stroke-dasharray="4 2"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite"/></circle><path d="M12 6v6l4 2"/></svg>',
  done: '<svg viewBox="0 0 24 24" fill="none" stroke="#0e8a16" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="8 12 11 15 16 9"/></svg>',
  error: '<svg viewBox="0 0 24 24" fill="none" stroke="#cf222e" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>'
};

function setQuery(q) {
  document.getElementById('queryInput').value = q;
}

function setStep(n, status, html) {
  var el = document.getElementById('step' + n);
  var iconEl = document.getElementById('step' + n + 'Icon');
  var detailEl = document.getElementById('step' + n + 'Detail');
  el.className = 'pipeline-step-item ' + status;
  iconEl.innerHTML = SVG_ICONS[status] || SVG_ICONS.pending;
  if (html !== undefined) detailEl.innerHTML = html;
}

function resetSteps() {
  for (var i = 1; i <= 4; i++) {
    setStep(i, 'pending', '<span style="color:#9ca3af">waiting...</span>');
  }
}

function esc(s) {
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

async function submitQuery() {
  var query = document.getElementById('queryInput').value.trim();
  if (!query) return;

  var btn = document.getElementById('queryBtn');
  var panel = document.getElementById('resultPanel');
  var content = document.getElementById('resultContent');
  var steps = document.getElementById('pipelineSteps');

  btn.disabled = true;
  btn.textContent = '\u67E5\u8A62\u4E2D...';
  panel.classList.add('show');
  content.style.display = 'none';
  steps.style.display = 'block';
  resetSteps();

  // Step 1: active
  setStep(1, 'active',
    'Synonym Map: comparing query against 5 prohibited alternative rules...<br>' +
    '<code>network banking &rarr; electronic banking</code> / ' +
    '<code>online banking &rarr; electronic banking</code> / ' +
    '<code>mobile banking &rarr; mobile banking (app)</code><br>' +
    'Source: glossary <code>prohibitedAlternatives</code> field &rarr; Azure AI Search Synonym Map (Solr format)'
  );

  var startTime = Date.now();
  var controller = new AbortController();
  var timeoutId = setTimeout(function() { controller.abort(); }, 90000);

  try {
    var fetchPromise = fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query }),
      signal: controller.signal
    });

    await new Promise(function(r) { setTimeout(r, 600); });

    // Step 1: done (placeholder)
    setStep(1, 'done', 'Synonym Map check complete. Waiting for API response...');

    // Step 2: active
    setStep(2, 'active',
      'Executing 3-route hybrid search:<br>' +
      '<strong>&bull; Route 1 &mdash; Vector Search</strong><br>' +
      '&nbsp;&nbsp;Model: <code>text-embedding-3-large</code> (3072 dimensions)<br>' +
      '&nbsp;&nbsp;Query text &rarr; embedding vector &rarr; cosine similarity against 63 chunk vectors<br><br>' +
      '<strong>&bull; Route 2 &mdash; BM25 Keyword Search</strong><br>' +
      '&nbsp;&nbsp;Analyzer: <code>zh-Hant.lucene</code> (Traditional Chinese tokenizer)<br>' +
      '&nbsp;&nbsp;Exact term matching on chunk content<br><br>' +
      '<strong>&bull; Route 3 &mdash; Metadata Term Match</strong><br>' +
      '&nbsp;&nbsp;Filter: <code>contained_terms</code> field exact match<br>' +
      '&nbsp;&nbsp;Definition chunks get 1.5x boost<br><br>' +
      'Fusion: <strong>Reciprocal Rank Fusion (k=60)</strong> &rarr; <strong>Semantic Ranker</strong> (cross-encoder rerank)'
    );

    await new Promise(function(r) { setTimeout(r, 1000); });

    // Step 2: done (placeholder)
    setStep(2, 'done', 'Hybrid search complete. Waiting for API response...');

    // Step 3: active
    setStep(3, 'active',
      'Querying Cosmos DB for term definitions and knowledge graph:<br><br>' +
      '<strong>&bull; Term Detection</strong><br>' +
      '&nbsp;&nbsp;Scan query text + retrieved chunk metadata for known term IDs<br><br>' +
      '<strong>&bull; Knowledge Graph 1-hop Expansion</strong><br>' +
      '&nbsp;&nbsp;Query <code>term-relations</code> container for connected terms<br>' +
      '&nbsp;&nbsp;Relation types: <code>broader_than</code>, <code>part_of</code>, <code>depends_on</code>, <code>conflicts_with</code><br><br>' +
      '<strong>&bull; 3-Tier Term Injection</strong><br>' +
      '&nbsp;&nbsp;Direct hit &rarr; <strong>Full</strong> format (definition + difference + prohibited alternatives)<br>' +
      '&nbsp;&nbsp;From chunks &rarr; <strong>Medium</strong> format (first 150 chars of definition)<br>' +
      '&nbsp;&nbsp;Graph expanded &rarr; <strong>Short</strong> format (60 char summary)<br>' +
      '&nbsp;&nbsp;Token budget: 6,000 tokens, allocated by priority until exhausted'
    );

    await new Promise(function(r) { setTimeout(r, 800); });

    // Step 3: done (placeholder)
    setStep(3, 'done', 'Term injection complete. Waiting for API response...');

    // Step 4: active
    setStep(4, 'active',
      'Assembling final prompt and calling Azure OpenAI GPT-4o:<br><br>' +
      '<strong>&bull; System Prompt (8 Rules)</strong><br>' +
      '&nbsp;&nbsp;1. Use enterprise definitions, never colloquial definitions<br>' +
      '&nbsp;&nbsp;2. Never use prohibited alternative terms<br>' +
      '&nbsp;&nbsp;3. First occurrence: "Full Name (Abbreviation)" format<br>' +
      '&nbsp;&nbsp;4. Every answer must cite regulation article numbers<br>' +
      '&nbsp;&nbsp;5. 3-level uncertainty handling (direct / indirect / out of scope)<br>' +
      '&nbsp;&nbsp;6-8. Self-check, structural fidelity, disclaimer<br><br>' +
      '<strong>&bull; Prompt Assembly</strong><br>' +
      '&nbsp;&nbsp;System Prompt + Dynamic Term Block + Retrieved Chunks + User Query<br><br>' +
      '<span style="color:#9ca3af">Serverless cold start may take 10-30 seconds on first call. Subsequent calls: 3-5 seconds.</span>'
    );

    // Wait for actual response
    var res = await fetchPromise;
    clearTimeout(timeoutId);
    var data = await res.json();
    var elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

    if (data.error) {
      var errorStep = data.budget ? 1 : 4;
      setStep(errorStep, 'error', '<strong>Error</strong>: ' + esc(data.error));
      if (data.budget) {
        setStep(2, 'pending', '');
        setStep(3, 'pending', '');
        setStep(4, 'pending', '');
      }
      return;
    }

    // === Update all steps with real results ===

    // Step 1: actual rewrite
    if (data.replacements && data.replacements.length > 0) {
      setStep(1, 'done',
        '<strong>Prohibited alternatives intercepted:</strong><br>' +
        data.replacements.map(function(r) { return '&bull; <code>' + esc(r) + '</code>'; }).join('<br>') + '<br><br>' +
        'Rewritten query: <code>' + esc(data.rewritten_query) + '</code>'
      );
    } else {
      setStep(1, 'done',
        'No prohibited alternatives detected in query. No rewrite needed.<br>' +
        'Current Synonym Map: 5 rules (network banking, online banking, digital banking, mobile banking, password)'
      );
    }

    // Step 2: actual search results
    var topChunks = data.search_results.slice(0, 3);
    setStep(2, 'done',
      '<strong>Found ' + data.search_results.length + ' relevant chunks</strong> (showing Top 3):<br><br>' +
      topChunks.map(function(c, i) {
        return '<strong>#' + (i+1) + '</strong> <code>' + esc(c.chunk_id) + '</code> (' + esc(c.article) + ')<br>' +
          '&nbsp;&nbsp;Hybrid Score: <code>' + c.score.toFixed(4) + '</code> | ' +
          'Semantic Reranker: <code>' + c.reranker_score.toFixed(2) + '</code>';
      }).join('<br><br>')
    );

    // Step 3: actual term injection
    var directCount = data.terms_injected.direct;
    var expandedCount = data.terms_injected.total - directCount;
    setStep(3, 'done',
      '<strong>Term injection results:</strong><br>' +
      '&bull; Direct hit terms (Full format): <strong>' + directCount + '</strong><br>' +
      '&bull; Graph-expanded terms (Medium/Short format): <strong>' + expandedCount + '</strong><br>' +
      '&bull; Total terms injected into System Prompt: <strong>' + data.terms_injected.total + '</strong>'
    );

    // Step 4: actual generation
    setStep(4, 'done',
      '<strong>Generation complete</strong> (' + elapsed + ' seconds)<br><br>' +
      '&bull; Prompt tokens: <code>' + data.usage.prompt_tokens + '</code><br>' +
      '&bull; Completion tokens: <code>' + data.usage.completion_tokens + '</code><br>' +
      '&bull; Total tokens: <code>' + data.usage.total_tokens + '</code>'
    );

    // Meta tags
    var meta = '';
    if (data.replacements && data.replacements.length > 0) {
      meta += data.replacements.map(function(r) {
        return '<span class="tag tag-rewrite">Synonym: ' + esc(r) + '</span>';
      }).join(' ');
    }
    meta += '<span class="tag tag-search">Chunks: ' + data.search_results.length + '</span> ';
    meta += '<span class="tag tag-terms">Terms: ' + directCount + ' direct / ' + data.terms_injected.total + ' total</span> ';
    meta += '<span class="tag tag-tokens">Tokens: ' + data.usage.total_tokens + ' (' + elapsed + 's)</span>';
    if (data.budget) {
      meta += ' <span class="tag" style="background:#e0e7ff;color:#3730a3;">Remaining: ' + data.budget.remaining + '/' + data.budget.limit + '</span>';
    }
    document.getElementById('resultMeta').innerHTML = meta;

    document.getElementById('resultAnswer').textContent = data.answer;

    var chunksText = data.search_results.map(function(c) {
      return c.chunk_id + ' (' + c.article + ') score=' + c.score.toFixed(4) + ' reranker=' + c.reranker_score.toFixed(2);
    }).join('\n');
    document.getElementById('resultChunks').textContent = 'Azure AI Search Results:\n' + chunksText;

    content.style.display = 'block';

  } catch (e) {
    clearTimeout(timeoutId);
    var msg;
    if (e.name === 'AbortError') {
      msg = 'Azure Functions Serverless cold start timeout (90s). Please click "Query" again - second attempt usually responds in 3-5 seconds.';
    } else {
      msg = e.message;
    }
    setStep(4, 'error',
      '<strong>Request failed</strong>: ' + esc(msg) + '<br><br>' +
      'Please click the query button to retry.'
    );
    content.style.display = 'none';
  } finally {
    btn.disabled = false;
    btn.textContent = '\u67E5\u8A62';
  }
}

document.getElementById('queryInput').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') submitQuery();
});

// Show warning if no API key
if (!API_KEY) {
  document.getElementById('noKeyWarning').style.display = 'block';
  document.getElementById('queryBtn').disabled = true;
  document.getElementById('queryBtn').title = 'API Key required';
}
