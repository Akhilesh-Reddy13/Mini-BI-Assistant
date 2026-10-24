import { useEffect, useRef, useState } from 'react'

const examples = [
  'What is the total revenue?',
  'Which product generated the highest revenue?',
  'Show the monthly revenue trend',
  'Which region generated the highest sales?',
]

const intentLabels = {
  total_revenue: 'Total revenue',
  top_product: 'Top product',
  monthly_trend: 'Monthly trend',
  top_region: 'Top region',
  compare_months: 'Month comparison',
}

async function requestJson(url, options) {
  let response
  try {
    response = await fetch(url, options)
  } catch {
    throw new Error('Could not reach the API. Make sure the FastAPI server is running on port 8000.')
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(body?.error?.message || 'The request could not be completed.')
  }
  return body
}

function BrandMark() {
  return (
    <div className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 36 36" fill="none">
        <rect x="2" y="2" width="32" height="32" rx="11" fill="currentColor" />
        <path d="M10 23.5V17m8 6.5V11m8 12.5v-9" stroke="white" strokeWidth="2.8" strokeLinecap="round" />
        <circle cx="10" cy="13" r="1.5" fill="#BFE5D5" />
      </svg>
    </div>
  )
}

function StatusDot({ state }) {
  const copy = state === 'ready' ? 'API connected' : state === 'checking' ? 'Checking API' : 'API offline'
  return (
    <div className={`connection connection-${state}`} title={copy}>
      <span className="connection-dot" />
      <span>{copy}</span>
    </div>
  )
}

function MetricTile({ label, value, note }) {
  return (
    <div className="metric-tile">
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
      {note && <span className="metric-note">{note}</span>}
    </div>
  )
}

function DataRows({ rows, labelField, amountField = 'revenue', countField = 'completed_transaction_count' }) {
  if (!rows?.length) return <p className="empty-support">No matching transaction data was found.</p>
  const maxValue = Math.max(...rows.map((row) => row.revenue_minor || 0), 1)
  return (
    <div className="data-rows">
      {rows.map((row) => {
        const width = Math.max(0, ((row.revenue_minor || 0) / maxValue) * 100)
        return (
          <div className="data-row" key={`${row[labelField]}-${row.month || ''}`}>
            <div className="data-row-top">
              <span className="data-row-name">{row[labelField]}</span>
              <strong>{row[amountField]}</strong>
            </div>
            <div className="bar-track" aria-hidden="true">
              <span className="bar-fill" style={{ width: `${width}%` }} />
            </div>
            <span className="data-row-meta">
              {row[countField]} completed {row[countField] === 1 ? 'transaction' : 'transactions'}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function SupportingData({ result }) {
  const support = result.supporting_data || {}
  const value = result.value || {}
  const months = support.months || value.months
  const ranked = support.ranked

  if (result.intent === 'total_revenue') {
    return (
      <div className="metrics-grid">
        <MetricTile label="Gross sales" value={support.gross_sales ?? '—'} />
        <MetricTile label="Discounts" value={support.discounts ?? '—'} />
        <MetricTile label="Completed rows" value={support.completed_transaction_count ?? '—'} />
        <MetricTile label="Returns excluded" value={support.returned_transactions_excluded ?? '—'} />
      </div>
    )
  }

  if (result.intent === 'top_product' || result.intent === 'top_region') {
    return <DataRows rows={ranked} labelField={result.intent === 'top_product' ? 'product' : 'region'} />
  }

  if (result.intent === 'monthly_trend' || result.intent === 'compare_months') {
    return <DataRows rows={months} labelField="month" />
  }

  return <p className="empty-support">Supporting figures are not available for this response.</p>
}

function ResultCard({ result }) {
  const unsupported = result.status === 'unsupported'
  const errorMessage = result.error?.message
  return (
    <section className={`result-card ${unsupported ? 'result-unsupported' : ''}`} aria-live="polite">
      <div className="result-heading">
        <div>
          <span className="section-kicker">{unsupported ? 'Try another question' : 'Answer'}</span>
          {result.intent && <h2>{intentLabels[result.intent] || 'Sales analysis'}</h2>}
        </div>
        {result.interpretation_source && (
          <span className="source-pill">
            <span className="source-spark">✦</span>
            {result.interpretation_source === 'groq' ? 'Groq interpreted' : 'Local interpretation'}
          </span>
        )}
      </div>

      {unsupported ? (
        <div className="unsupported-message">
          <span className="notice-icon" aria-hidden="true">i</span>
          <p>{errorMessage || 'I could not map that to one of the supported sales questions.'}</p>
        </div>
      ) : (
        <>
          <p className="answer-copy">{result.answer}</p>
          {result.value?.amount && (
            <div className="headline-value">
              <span>Net revenue</span>
              <strong>{result.value.amount}</strong>
              <small>currency unspecified</small>
            </div>
          )}
          {result.value?.leaders?.length > 0 && (
            <div className="leader-chips">
              {result.value.leaders.map((leader) => (
                <span className="leader-chip" key={leader.product || leader.region}>
                  <span className="leader-check">✓</span>
                  {leader.product || leader.region}
                  <b>{leader.revenue}</b>
                </span>
              ))}
            </div>
          )}
          <div className="support-block">
            <div className="support-heading">
              <h3>Supporting figures</h3>
              <span>From your sales database</span>
            </div>
            <SupportingData result={result} />
            {result.supporting_data?.note && <p className="support-note">{result.supporting_data.note}</p>}
          </div>
          <div className="metric-definition">
            <span className="definition-icon" aria-hidden="true">ƒ</span>
            <p>{result.metric}</p>
          </div>
        </>
      )}
    </section>
  )
}

export default function App() {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [apiState, setApiState] = useState('checking')
  const inputRef = useRef(null)

  useEffect(() => {
    let active = true
    requestJson('/api/health')
      .then(() => active && setApiState('ready'))
      .catch(() => active && setApiState('offline'))
    return () => { active = false }
  }, [])

  async function submitQuestion(event) {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed || loading) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const response = await requestJson('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: trimmed }),
      })
      setResult(response)
      setApiState('ready')
    } catch (requestError) {
      setError(requestError.message)
      setApiState('offline')
    } finally {
      setLoading(false)
    }
  }

  function selectExample(example) {
    setQuestion(example)
    setResult(null)
    setError('')
    inputRef.current?.focus()
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Sales Intelligence home">
          <BrandMark />
          <span>Sales<span className="brand-accent">Lens</span></span>
        </a>
        <div className="topbar-right">
          <span className="dataset-label"><span className="dataset-icon">▦</span> Sales transactions</span>
          <StatusDot state={apiState} />
        </div>
      </header>

      <main id="top" className="main-content">
        <section className="hero">
          <div className="eyebrow"><span className="eyebrow-star">✦</span> YOUR BUSINESS, IN FOCUS</div>
          <h1>Ask your sales data<br /><span>anything.</span></h1>
          <p className="hero-copy">Clear answers from your transactions, with the numbers behind them.</p>
        </section>

        <section className="question-panel" aria-label="Ask a sales question">
          <form onSubmit={submitQuestion}>
            <label className="input-label" htmlFor="question">What would you like to know?</label>
            <div className="input-wrap">
              <textarea
                id="question"
                ref={inputRef}
                value={question}
                onChange={(event) => setQuestion(event.target.value.slice(0, 1000))}
                onKeyDown={(event) => {
                  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') submitQuestion(event)
                }}
                placeholder="e.g. Which product generated the highest revenue?"
                rows={2}
                maxLength={1000}
                aria-describedby="question-hint"
                disabled={loading}
              />
              <div className="input-actions">
                <span id="question-hint" className="keyboard-hint">Press <kbd>Ctrl</kbd> + <kbd>Enter</kbd> to ask</span>
                <span className="char-count">{question.length}/1000</span>
              </div>
            </div>
            <div className="form-footer">
              <span className="privacy-note"><span className="lock-icon">◈</span> Answers are calculated from your sales database</span>
              <button className="ask-button" type="submit" disabled={!question.trim() || loading}>
                {loading ? <><span className="spinner" /> Thinking</> : <>Ask question <span aria-hidden="true">↗</span></>}
              </button>
            </div>
          </form>
        </section>

        <section className="examples-section" aria-labelledby="examples-title">
          <div className="examples-heading">
            <h2 id="examples-title">Try asking</h2>
            <span>Start with a question like</span>
          </div>
          <div className="example-list">
            {examples.map((example, index) => (
              <button className="example-chip" type="button" onClick={() => selectExample(example)} key={example}>
                <span className={`example-index example-index-${index + 1}`}>{String(index + 1).padStart(2, '0')}</span>
                <span>{example}</span>
                <span className="chip-arrow" aria-hidden="true">↗</span>
              </button>
            ))}
            <button
              className="example-chip example-chip-wide"
              type="button"
              onClick={() => selectExample('How did revenue change between January and February 2026?')}
            >
              <span className="example-index example-index-5">05</span>
              <span>How did revenue change between January and February 2026?</span>
              <span className="chip-arrow" aria-hidden="true">↗</span>
            </button>
          </div>
        </section>

        {loading && (
          <section className="loading-card" aria-live="polite">
            <span className="loading-orbit"><span /></span>
            <div><strong>Looking through your sales data</strong><span>Calculating from completed transactions…</span></div>
          </section>
        )}

        {error && (
          <div className="error-banner" role="alert">
            <span className="error-symbol">!</span>
            <span>{error}</span>
          </div>
        )}

        {result && !loading && <ResultCard result={result} />}

        <footer className="page-footer">
          <span>SalesLens <span className="footer-separator">·</span> Mini BI Assistant</span>
          <span>Every answer backed by a database calculation</span>
        </footer>
      </main>
    </div>
  )
}
