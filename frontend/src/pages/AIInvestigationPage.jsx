import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertCircle,
  Archive,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  FileText,
  FileDown,
  LoaderCircle,
  MessageCircle,
  Plus,
  RefreshCw,
  Send,
  Upload,
  X,
} from 'lucide-react'
import api from '../services/api'
import { formatDateTime } from '../utils/dateTime'
import './AIInvestigationPage.css'

const activeRunStatuses = new Set(['queued', 'running', 'cancel_requested'])

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return 'Size unavailable'
  return `${(bytes / (1024 ** 3)).toFixed(1)} GiB`
}

function formatDate(value) {
  if (!value) return 'Just now'
  return formatDateTime(value)
}

function statusLabel(status) {
  return (status || 'unknown').replaceAll('_', ' ')
}

function defaultModel(environment) {
  const recommendation = environment?.recommendation?.model_name
  const models = environment?.models || []
  return models.find((model) => model.name === recommendation)?.name
    || [...models]
      .sort((left, right) => (left.size_bytes ?? Infinity) - (right.size_bytes ?? Infinity))[0]?.name
    || ''
}

function AIInvestigationPage() {
  const [environment, setEnvironment] = useState(null)
  const [investigations, setInvestigations] = useState([])
  const [standardInvestigations, setStandardInvestigations] = useState([])
  const [investigationId, setInvestigationId] = useState('')
  const [investigation, setInvestigation] = useState(null)
  const [runs, setRuns] = useState([])
  const [selectedRun, setSelectedRun] = useState(null)
  const [chatMessages, setChatMessages] = useState([])
  const [chatInput, setChatInput] = useState('')
  const [reports, setReports] = useState([])
  const [reviewDrafts, setReviewDrafts] = useState({})
  const [selectedStandardId, setSelectedStandardId] = useState('')
  const [standardDetail, setStandardDetail] = useState(null)
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([])
  const [selectedAIFile, setSelectedAIFile] = useState(null)
  const [selectedModel, setSelectedModel] = useState('')
  const [form, setForm] = useState({
    title: '',
    description: '',
    customInstructions: '',
    analysisDepth: 'quick',
  })
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const models = environment?.models || []
  const linkedStandardIds = useMemo(
    () => new Set((investigation?.sources || []).map((source) => source.investigation_id)),
    [investigation],
  )
  const attachedDocumentIds = useMemo(
    () => new Set((investigation?.documents || []).map((document) => document.document_id).filter(Boolean)),
    [investigation],
  )
  const activeRun = runs.find((run) => activeRunStatuses.has(run.status))
  const latestRun = selectedRun || runs[0] || null
  const selectedStandardIsLinked = selectedStandardId
    ? linkedStandardIds.has(Number(selectedStandardId))
    : false
  const modelIsWorking = activeRun && !['queued', 'evidence_retrieval'].includes(activeRun.stage)

  const refreshEnvironment = useCallback(async () => {
    try {
      const result = await api.getAIEnvironment()
      setEnvironment(result)
      setSelectedModel((current) => (
        current && result.models.some((model) => model.name === current)
          ? current
          : defaultModel(result)
      ))
    } catch (requestError) {
      setError(requestError.message)
    }
  }, [])

  const refreshDetail = useCallback(async (id) => {
    if (!id) return
    const [detail, runList, chatHistory, reportList] = await Promise.all([
      api.getAIInvestigation(id),
      api.getAIAnalysisRuns(id),
      api.getAIChatHistory(id),
      api.getAIReports(id),
    ])
    setInvestigation(detail)
    if (detail.selected_model) setSelectedModel(detail.selected_model)
    setRuns(runList)
    setChatMessages(chatHistory)
    setReports(reportList)
    setSelectedRun((current) => {
      if (current && runList.some((run) => run.id === current.id)) return current
      return null
    })
  }, [])

  useEffect(() => {
    let mounted = true
    async function loadWorkspace() {
      setLoading(true)
      try {
        const [environmentResult, aiItems, standardItems] = await Promise.all([
          api.getAIEnvironment(),
          api.getAIInvestigations(),
          api.getInvestigations(),
        ])
        if (!mounted) return
        setEnvironment(environmentResult)
        setInvestigations(aiItems)
        setStandardInvestigations(standardItems)
        setSelectedModel(defaultModel(environmentResult))
        if (aiItems.length) setInvestigationId(String(aiItems[0].id))
      } catch (requestError) {
        if (mounted) setError(requestError.message)
      } finally {
        if (mounted) setLoading(false)
      }
    }
    loadWorkspace()
    return () => { mounted = false }
  }, [])

  useEffect(() => {
    if (!investigationId) {
      setInvestigation(null)
      setRuns([])
      setSelectedRun(null)
      return
    }
    let mounted = true
    setInvestigation(null)
    setRuns([])
    setSelectedRun(null)
    setError('')
    Promise.all([
      api.getAIInvestigation(investigationId),
      api.getAIAnalysisRuns(investigationId),
      api.getAIChatHistory(investigationId),
      api.getAIReports(investigationId),
    ]).then(([detail, runList, chatHistory, reportList]) => {
      if (!mounted) return
      setInvestigation(detail)
      if (detail.selected_model) setSelectedModel(detail.selected_model)
      setRuns(runList)
      setChatMessages(chatHistory)
      setReports(reportList)
      setSelectedRun(null)
      setSelectedStandardId('')
      setStandardDetail(null)
    }).catch((requestError) => {
      if (mounted) setError(requestError.message)
    })
    return () => { mounted = false }
  }, [investigationId])

  useEffect(() => {
    if (!investigationId || !activeRun) return undefined
    const timer = window.setInterval(async () => {
      try {
        const [detail, runList] = await Promise.all([
          api.getAIInvestigation(investigationId),
          api.getAIAnalysisRuns(investigationId),
        ])
        setInvestigation(detail)
        setRuns(runList)
        const currentRun = runList.find((run) => run.id === activeRun.id)
        if (currentRun && !activeRunStatuses.has(currentRun.status)) {
          setSelectedRun(await api.getAIAnalysisRun(investigationId, currentRun.id))
        }
      } catch (requestError) {
        setError(requestError.message)
      }
    }, 2000)
    return () => window.clearInterval(timer)
  }, [activeRun?.id, investigationId])

  const detailRunId = selectedRun?.id || runs[0]?.id
  useEffect(() => {
    if (!detailRunId || !investigationId) return
    let mounted = true
    api.getAIAnalysisRun(investigationId, detailRunId)
      .then((detail) => {
        if (mounted && (!selectedRun || selectedRun.id === detail.id)) {
          setSelectedRun(detail)
        }
      })
      .catch((requestError) => { if (mounted) setError(requestError.message) })
    return () => { mounted = false }
  }, [detailRunId, investigationId])

  useEffect(() => {
    setSelectedDocumentIds([])
    if (!selectedStandardId) {
      setStandardDetail(null)
      return
    }
    let mounted = true
    api.getInvestigation(selectedStandardId)
      .then((detail) => { if (mounted) setStandardDetail(detail) })
      .catch((requestError) => { if (mounted) setError(requestError.message) })
    return () => { mounted = false }
  }, [selectedStandardId])

  const updateForm = (event) => {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
  }

  const refreshLists = async (selectId) => {
    const [aiItems, standardItems] = await Promise.all([
      api.getAIInvestigations(),
      api.getInvestigations(),
    ])
    setInvestigations(aiItems)
    setStandardInvestigations(standardItems)
    if (selectId) setInvestigationId(String(selectId))
  }

  const createInvestigation = async (event) => {
    event.preventDefault()
    setBusy('create')
    setError('')
    try {
      const created = await api.createAIInvestigation({
        title: form.title,
        description: form.description || null,
        custom_instructions: form.customInstructions || null,
        selected_model: selectedModel || null,
        analysis_depth: form.analysisDepth,
      })
      setNotice('AI investigation created.')
      setForm({ title: '', description: '', customInstructions: '', analysisDepth: 'quick' })
      await refreshLists(created.id)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy('')
    }
  }

  const selectModel = async (event) => {
    const model = event.target.value
    setSelectedModel(model)
    if (!investigation || !model) return

    setBusy('save')
    setError('')
    try {
      const updated = await api.updateAIInvestigation(investigation.id, {
        selected_model: model,
      })
      setInvestigation(updated)
      setNotice(`Model saved: ${model}`)
    } catch (requestError) {
      setSelectedModel(investigation.selected_model || defaultModel(environment))
      setError(requestError.message)
    } finally {
      setBusy('')
    }
  }

  const linkSource = async () => {
    if (!investigation || !selectedStandardId) return
    setBusy('link')
    setError('')
    try {
      await api.linkStandardInvestigation(investigation.id, selectedStandardId)
      await refreshDetail(investigation.id)
      setNotice('Source linked. Select the documents you want to attach below.')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy('')
    }
  }

  const attachDocuments = async () => {
    const documentIds = selectedDocumentIds.filter((id) => !attachedDocumentIds.has(id))
    if (!investigation || !documentIds.length) return
    setBusy('attach')
    setError('')
    try {
      const updated = await api.selectAIStandardDocuments(investigation.id, documentIds)
      setInvestigation(updated)
      setSelectedDocumentIds([])
      setNotice(`${documentIds.length} source document(s) attached to this AI investigation.`)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy('')
    }
  }

  const uploadDocument = async () => {
    if (!investigation || !selectedAIFile) return
    setBusy('upload')
    setError('')
    try {
      const updated = await api.uploadAIDocument(investigation.id, selectedAIFile)
      setInvestigation(updated)
      setSelectedAIFile(null)
      setNotice('Document added to the AI-only workspace.')
      const input = document.getElementById('ai-document-input')
      if (input) input.value = ''
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy('')
    }
  }

  const startAnalysis = async () => {
    if (!investigation) return
    setBusy('analysis')
    setError('')
    try {
      const run = await api.startAIAnalysis(investigation.id, { model: selectedModel })
      setSelectedRun(run)
      await refreshDetail(investigation.id)
      setNotice('Analysis queued. Progress will update automatically.')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy('')
    }
  }

  const cancelAnalysis = async () => {
    if (!investigation || !activeRun) return
    setBusy('cancel')
    setError('')
    try {
      await api.cancelAIAnalysis(investigation.id, activeRun.id)
      await refreshDetail(investigation.id)
      setNotice('Cancellation requested. It takes effect at the next stage boundary.')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy('')
    }
  }

  const sendChat = async (event) => {
    event.preventDefault()
    const message = chatInput.trim()
    if (!investigation || !message || busy) return
    setBusy('chat')
    setError('')
    try {
      const newMessages = await api.sendAIChatMessage(investigation.id, message)
      setChatMessages((current) => [...current, ...newMessages])
      setChatInput('')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy('')
    }
  }

  const reviewFinding = async (finding) => {
    if (!investigation) return
    const draft = reviewDrafts[finding.id] || {}
    setBusy(`review-${finding.id}`)
    setError('')
    try {
      await api.reviewAIFinding(investigation.id, finding.id, {
        review_status: draft.review_status || 'needs_review',
        reviewer: draft.reviewer || null,
        comment: draft.comment || null,
      })
      const updatedRun = await api.getAIAnalysisRun(investigation.id, latestRun.id)
      setSelectedRun(updatedRun)
      setNotice('Finding review saved to the audit history.')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy('')
    }
  }

  const generateAIReport = async () => {
    if (!investigation || latestRun?.status !== 'completed') return
    setBusy('ai-report')
    setError('')
    try {
      await api.generateAIReport(investigation.id, latestRun.id)
      setReports(await api.getAIReports(investigation.id))
      setNotice('AI investigation PDF report generated.')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy('')
    }
  }

  const archiveInvestigation = async () => {
    if (!investigation || !window.confirm(`Archive "${investigation.title}"?`)) return
    setBusy('archive')
    setError('')
    try {
      await api.archiveAIInvestigation(investigation.id)
      setInvestigationId('')
      setInvestigation(null)
      setChatMessages([])
      setReports([])
      await refreshLists()
      setNotice('AI investigation archived.')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy('')
    }
  }

  const refreshNow = async () => {
    setBusy('refresh')
    await refreshEnvironment()
    if (investigationId) {
      try {
        await refreshDetail(investigationId)
      } catch (requestError) {
        setError(requestError.message)
      }
    }
    setBusy('')
  }

  if (loading) {
    return <div className="ai-loading"><LoaderCircle className="ai-spin" size={24} /> Loading AI workspace…</div>
  }

  return (
    <div className="ai-workspace">
      <header className="ai-page-header">
        <div>
          <span className="ai-eyebrow"><BrainCircuit size={15} /> LOCAL MODEL WORKSPACE</span>
          <h1>AI Investigation</h1>
          <p>Run a separate, evidence-grounded review using an installed local Ollama model.</p>
        </div>
        <button className="button-secondary ai-refresh" onClick={refreshNow} disabled={busy !== ''}>
          <RefreshCw size={16} className={busy === 'refresh' ? 'ai-spin' : ''} /> Refresh runtime
        </button>
      </header>

      {error && <div className="ai-alert ai-alert-error" role="alert"><AlertCircle size={18} /><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss error"><X size={16} /></button></div>}
      {notice && <div className="ai-alert ai-alert-success" role="status"><CheckCircle2 size={18} /><span>{notice}</span><button onClick={() => setNotice('')} aria-label="Dismiss notice"><X size={16} /></button></div>}

      <section className={`ai-runtime-card ${environment?.status === 'available' ? 'ai-runtime-ready' : ''}`}>
        <div className="ai-runtime-icon"><BrainCircuit size={21} /></div>
        <div className="ai-runtime-copy">
          <strong>{environment?.status === 'available' ? 'Ollama runtime available' : 'Ollama runtime unavailable'}</strong>
          <span>{environment?.status === 'available'
            ? `${environment.version ? `Ollama ${environment.version} · ` : ''}${models.length} installed model(s) · ${environment.endpoint}`
            : environment?.guidance || environment?.error || 'Check the configured local Ollama service.'}</span>
          {environment?.recommendation && <small>Suggested: {environment.recommendation.model_name}. {environment.recommendation.basis}</small>}
          {environment?.warnings?.map((warning) => <small key={warning}>{warning}</small>)}
        </div>
        <span className={`ai-runtime-status ${environment?.status === 'available' ? 'is-ready' : ''}`}>
          {environment?.status === 'available' ? 'READY' : statusLabel(environment?.status).toUpperCase()}
        </span>
      </section>

      <div className="ai-workspace-grid">
        <aside className="ai-sidebar">
          <div className="ai-panel ai-list-panel">
            <div className="ai-panel-heading">
              <div><span className="ai-section-label">WORKSPACE</span><h2>Your investigations</h2></div>
              <span className="ai-count">{investigations.length}</span>
            </div>
            {investigations.length ? (
              <div className="ai-investigation-list">
                {investigations.map((item) => (
                  <button
                    className={`ai-investigation-item ${String(item.id) === investigationId ? 'is-selected' : ''}`}
                    key={item.id}
                    onClick={() => setInvestigationId(String(item.id))}
                  >
                    <span className="ai-item-icon"><FileText size={17} /></span>
                    <span className="ai-item-copy"><strong>{item.title}</strong><small>{item.document_count} documents · {statusLabel(item.status)}</small></span>
                    <ChevronDown size={15} className="ai-item-chevron" />
                  </button>
                ))}
              </div>
            ) : <p className="ai-muted ai-empty-list">No AI investigations yet.</p>}
          </div>

          <form className="ai-panel ai-create-panel" onSubmit={createInvestigation}>
            <span className="ai-section-label">NEW WORKSPACE</span>
            <h2>Create AI investigation</h2>
            <label>Title<input name="title" value={form.title} onChange={updateForm} required maxLength={255} placeholder="e.g. Vendor invoice review" /></label>
            <label>Description<textarea name="description" value={form.description} onChange={updateForm} rows={2} placeholder="What should this workspace examine?" /></label>
            <label>Analysis depth<select name="analysisDepth" value={form.analysisDepth} onChange={updateForm}><option value="quick">Quick · one model pass, max 2 minutes</option><option value="standard">Standard · multi-stage</option><option value="deep">Deep · multi-stage</option></select></label>
            <label>Investigator instructions<textarea name="customInstructions" value={form.customInstructions} onChange={updateForm} rows={3} maxLength={8000} placeholder="Optional scope and context. Evidence rules cannot be overridden." /></label>
            <button type="submit" className="button-primary ai-full-button" disabled={busy !== ''}>
              <Plus size={17} /> {busy === 'create' ? 'Creating…' : 'Create workspace'}
            </button>
          </form>
        </aside>

        <main className="ai-main-column">
          {!investigation ? (
            <div className="ai-panel ai-welcome">
              <div className="ai-welcome-icon"><BrainCircuit size={29} /></div>
              <h2>Start an isolated AI investigation</h2>
              <p>Create a workspace to attach existing evidence selectively or upload files for AI-only analysis. Standard Investigation records are never changed by AI runs.</p>
            </div>
          ) : (
            <>
              <section className="ai-panel ai-case-header">
                <div>
                  <span className="ai-section-label">AI INVESTIGATION #{investigation.id}</span>
                  <h2>{investigation.title}</h2>
                  <p>{investigation.description || 'No description provided.'}</p>
                </div>
                <button className="ai-icon-button" onClick={archiveInvestigation} disabled={busy !== ''} title="Archive investigation" aria-label="Archive investigation"><Archive size={17} /></button>
              </section>

              <section className="ai-panel ai-model-panel">
                <div className="ai-panel-heading">
                  <div><span className="ai-section-label">LOCAL INFERENCE</span><h2>Model and analysis</h2></div>
                  <span className="ai-privacy-chip">Ollama · local</span>
                </div>
                <div className="ai-model-controls">
                  <label className="ai-grow">Installed model
                  <select value={selectedModel} onChange={selectModel} disabled={!models.length || busy !== ''}>
                    {!models.length && <option value="">No installed models detected</option>}
                    {models.map((model) => <option key={model.name} value={model.name}>{model.name} · {formatBytes(model.size_bytes)}</option>)}
                  </select>
                  </label>
                  <button className="button-primary" onClick={startAnalysis} disabled={
                  busy !== '' || environment?.status !== 'available' || !selectedModel
                    || !investigation.documents?.length || Boolean(activeRun)
                  }>
                    <BrainCircuit size={16} /> {busy === 'analysis' ? 'Queuing…' : 'Start analysis'}
                  </button>
                </div>
                {environment?.status !== 'available' && <p className="ai-inline-note">Start Ollama to run analysis. Creating workspaces and attaching evidence does not require the runtime.</p>}
                {environment?.status === 'available' && !models.length && <p className="ai-inline-note">Install a model in Ollama, then refresh this page. Decipher does not download models automatically.</p>}
                {activeRun && (
                  <div className="ai-progress">
                    <div className="ai-progress-heading">
                      <span><LoaderCircle size={15} className="ai-spin" /> {modelIsWorking ? 'Local model is analyzing evidence' : statusLabel(activeRun.stage || activeRun.status)}</span>
                      <strong>{modelIsWorking ? 'In progress' : `${activeRun.progress}%`}</strong>
                    </div>
                    <p className="ai-inline-note">
                      {modelIsWorking
                        ? 'Model inference can take a few minutes. The progress bar is indeterminate while the local model responds.'
                        : 'Preparing the selected evidence for analysis.'}
                    </p>
                    <div
                      className={`ai-progress-track ${modelIsWorking ? 'is-indeterminate' : ''}`}
                      role="progressbar"
                      aria-label={modelIsWorking ? 'Local model analysis in progress' : 'Analysis progress'}
                      aria-valuemin="0"
                      aria-valuemax="100"
                      aria-valuenow={modelIsWorking ? undefined : activeRun.progress}
                    >
                      <span style={modelIsWorking ? undefined : { width: `${activeRun.progress}%` }} />
                    </div>
                    <button className="ai-text-button" onClick={cancelAnalysis} disabled={busy !== ''}>Request cancellation</button>
                  </div>
                )}
              </section>

              <section className="ai-panel ai-evidence-panel">
                <div className="ai-panel-heading">
                  <div><span className="ai-section-label">EVIDENCE</span><h2>Documents and sources</h2></div>
                  <span className="ai-count">{investigation.documents?.length || 0}</span>
                </div>
                <div className="ai-evidence-grid">
                  <div className="ai-evidence-column">
                    <h3>Connect source documents</h3>
                    <p className="ai-muted">Choose a standard investigation and link it first. Then select only the documents this AI review should use.</p>
                    <div className="ai-inline-controls">
                      <select value={selectedStandardId} onChange={(event) => setSelectedStandardId(event.target.value)}>
                        <option value="">Choose an investigation</option>
                        {standardInvestigations.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.title}{linkedStandardIds.has(item.id) ? ' · linked' : ''}
                          </option>
                        ))}
                      </select>
                      <button className="button-secondary" onClick={linkSource} disabled={!selectedStandardId || selectedStandardIsLinked || busy !== ''}>
                        {selectedStandardIsLinked ? 'Source linked' : 'Link source'}
                      </button>
                    </div>
                    {standardDetail && (
                      <div className="ai-source-picker">
                        {!selectedStandardIsLinked ? (
                          <p className="ai-muted">Link this investigation to enable document selection.</p>
                        ) : standardDetail.documents?.length ? standardDetail.documents.map((doc) => (
                          <label className="ai-check-row" key={doc.id}>
                            <input type="checkbox" checked={selectedDocumentIds.includes(doc.id) || attachedDocumentIds.has(doc.id)} disabled={attachedDocumentIds.has(doc.id)} onChange={(event) => setSelectedDocumentIds((current) => event.target.checked ? [...current, doc.id] : current.filter((id) => id !== doc.id))} />
                            <span><strong>{doc.filename}</strong><small>{doc.doc_type || 'Document'} · {statusLabel(doc.processing_status)}</small></span>
                          </label>
                        )) : <p className="ai-muted">No documents are available in this standard investigation.</p>}
                        {selectedStandardIsLinked && selectedDocumentIds.some((id) => !attachedDocumentIds.has(id)) && <button className="button-secondary ai-attach-button" onClick={attachDocuments} disabled={busy !== ''}>Attach selected documents</button>}
                      </div>
                    )}
                    {investigation.sources?.length > 0 && (
                      <div className="ai-linked-sources">
                        {investigation.sources.map((source) => <span key={source.investigation_id}><CheckCircle2 size={14} /> {source.title}</span>)}
                      </div>
                    )}
                  </div>
                  <div className="ai-evidence-column ai-upload-column">
                    <h3>Upload AI-only evidence</h3>
                    <p className="ai-muted">Files stay in this AI workspace and are not sent through standard processing.</p>
                    <input id="ai-document-input" type="file" accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp" onChange={(event) => setSelectedAIFile(event.target.files?.[0] || null)} />
                    <button className="button-secondary" onClick={uploadDocument} disabled={!selectedAIFile || busy !== ''}><Upload size={15} /> {busy === 'upload' ? 'Uploading…' : 'Upload file'}</button>
                  </div>
                </div>
                <div className="ai-document-list">
                  {investigation.documents?.length ? investigation.documents.map((doc) => (
                    <div className="ai-document-row" key={doc.id}>
                      <FileText size={16} />
                      <span><strong>{doc.filename}</strong><small>{doc.source_type === 'standard_document' ? 'Linked source' : 'AI-only upload'} · {statusLabel(doc.processing_status)}</small></span>
                      <span className="ai-document-check"><CheckCircle2 size={15} /> Attached</span>
                    </div>
                  )) : <p className="ai-muted">Attach or upload evidence to begin.</p>}
                </div>
              </section>

              <section className="ai-panel ai-chat-panel">
                <div className="ai-panel-heading">
                  <div><span className="ai-section-label">SOURCE-GROUNDED CHAT</span><h2>Ask about this evidence</h2></div>
                  <MessageCircle size={18} />
                </div>
                <p className="ai-muted">Answers use evidence attached to this workspace and show verified source quotations when available.</p>
                <div className="ai-chat-history" aria-live="polite">
                  {chatMessages.length ? chatMessages.map((message) => (
                    <article className={`ai-chat-message role-${message.role}`} key={message.id}>
                      <strong>{message.role === 'assistant' ? 'Investigation assistant' : 'You'}</strong>
                      <p>{message.content}</p>
                      {message.citations?.map((citation) => (
                        <blockquote className="ai-quote" key={`${message.id}-${citation.evidence_id}`}>
                          <span>{citation.filename || 'Evidence'} · Page {citation.page_number || '—'}</span>
                          <p>“{citation.quote}”</p>
                        </blockquote>
                      ))}
                    </article>
                  )) : <p className="ai-muted">Chat history for this investigation will appear here.</p>}
                </div>
                <form className="ai-chat-form" onSubmit={sendChat}>
                  <textarea aria-label="Message the investigation assistant" value={chatInput} onChange={(event) => setChatInput(event.target.value)} maxLength={4000} rows={2} placeholder="Ask a question about the attached source material…" />
                  <button className="button-primary" type="submit" disabled={!chatInput.trim() || !investigation.documents?.length || environment?.status !== 'available' || busy !== ''}>
                    <Send size={15} /> {busy === 'chat' ? 'Sending…' : 'Ask'}
                  </button>
                </form>
              </section>

              <section className="ai-panel ai-results-panel">
                <div className="ai-panel-heading">
                  <div><span className="ai-section-label">ANALYSIS OUTPUT</span><h2>Findings and evidence</h2></div>
                  <div className="ai-result-actions">
                    {latestRun?.status === 'completed' && <button className="button-secondary" onClick={generateAIReport} disabled={busy !== ''}><FileDown size={15} /> {busy === 'ai-report' ? 'Generating…' : 'Export PDF'}</button>}
                    {runs.length > 1 && <select aria-label="Choose analysis run" value={latestRun?.id || ''} onChange={async (event) => {
                    try {
                      setSelectedRun(await api.getAIAnalysisRun(investigation.id, event.target.value))
                    } catch (requestError) {
                      setError(requestError.message)
                    }
                  }}>{runs.map((run) => <option key={run.id} value={run.id}>Run #{run.id} · {statusLabel(run.status)}</option>)}</select>}
                  </div>
                </div>
                {!latestRun ? <p className="ai-muted">Run an analysis to see source-checked findings here.</p> : (
                  <>
                    <div className="ai-run-summary">
                      <span className={`ai-run-state state-${latestRun.status}`}>{statusLabel(latestRun.status)}</span>
                      <span>{latestRun.model || latestRun.model_name}</span>
                      <span>{formatDate(latestRun.created_at)}</span>
                    </div>
                    {latestRun.error && <div className="ai-alert ai-alert-error"><AlertCircle size={17} />{latestRun.error}</div>}
                    {latestRun.findings?.length ? latestRun.findings.map((finding) => (
                      <article className="ai-finding-card" key={finding.id}>
                        <div className="ai-finding-heading">
                          <div><span className={`ai-severity severity-${finding.severity}`}>{finding.severity}</span><h3>{finding.title}</h3></div>
                          <span>{Math.round(finding.confidence * 100)}% confidence</span>
                        </div>
                        <p>{finding.description}</p>
                        {finding.reasoning && <p className="ai-reasoning">{finding.reasoning}</p>}
                        {finding.recommended_action && <p className="ai-action"><strong>Suggested follow-up:</strong> {finding.recommended_action}</p>}
                        {finding.evidence?.map((evidence) => (
                          <blockquote className="ai-quote" key={evidence.id}>
                            <span>Page {evidence.page_number || '—'} · {evidence.verification_status}</span>
                            <p>“{evidence.quote}”</p>
                          </blockquote>
                        ))}
                        {finding.alternative_explanations?.length > 0 && <details className="ai-alternatives"><summary>Alternative explanations</summary><ul>{finding.alternative_explanations.map((alternative, index) => <li key={`${finding.id}-alternative-${index}`}>{typeof alternative === 'string' ? alternative : JSON.stringify(alternative)}</li>)}</ul></details>}
                        <div className="ai-review-form">
                          <label>Review decision
                            <select value={reviewDrafts[finding.id]?.review_status || finding.review_status || 'needs_review'} onChange={(event) => setReviewDrafts((current) => ({ ...current, [finding.id]: { ...current[finding.id], review_status: event.target.value } }))}>
                              <option value="needs_review">Needs review</option>
                              <option value="accepted">Accepted</option>
                              <option value="rejected">Rejected</option>
                            </select>
                          </label>
                          <label>Reviewer<input value={reviewDrafts[finding.id]?.reviewer || ''} maxLength={255} onChange={(event) => setReviewDrafts((current) => ({ ...current, [finding.id]: { ...current[finding.id], reviewer: event.target.value } }))} placeholder="Optional name" /></label>
                          <label>Review note<textarea rows={2} maxLength={4000} value={reviewDrafts[finding.id]?.comment || ''} onChange={(event) => setReviewDrafts((current) => ({ ...current, [finding.id]: { ...current[finding.id], comment: event.target.value } }))} placeholder="Document your assessment or follow-up." /></label>
                          <button className="button-secondary" onClick={() => reviewFinding(finding)} disabled={busy !== ''}>{busy === `review-${finding.id}` ? 'Saving…' : 'Save review'}</button>
                        </div>
                        {finding.reviews?.length > 0 && <details className="ai-review-history"><summary>Review history ({finding.reviews.length})</summary>{finding.reviews.map((review) => <p key={review.id}><strong>{statusLabel(review.review_status)}</strong> · {review.reviewer || 'Reviewer not named'} · {formatDate(review.created_at)}{review.comment ? ` — ${review.comment}` : ''}</p>)}</details>}
                      </article>
                    )) : <p className="ai-muted">{activeRun ? 'Findings will appear after analysis completes.' : 'No source-verified findings were produced for this run.'}</p>}
                  </>
                )}
                <div className="ai-report-history">
                  <h3>Generated AI reports</h3>
                  {reports.length ? reports.map((report) => (
                    <a className="ai-report-link" key={report.id} href={api.getAIReportDownloadUrl(report.download_url)} download>
                      <FileDown size={15} /> Run #{report.analysis_run_id} PDF · {formatDate(report.created_at)}
                    </a>
                  )) : <p className="ai-muted">No AI run PDFs have been generated yet.</p>}
                </div>
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  )
}

export default AIInvestigationPage
