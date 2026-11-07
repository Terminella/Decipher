
import { useEffect, useMemo, useState } from 'react'
import FindingCard from '../components/FindingCard'
import api from '../services/api'
import {
  Plus,
  Search,
  Filter,
  FileSearch,
  AlertTriangle,
  ShieldAlert,
  Clock3,
  CheckCircle2,
  X,
  Eye,
  Pencil,
  Trash2,
  ArrowLeft,
  CalendarDays,
} from 'lucide-react'
import StatusPill from '../components/StatusPill'
import { formatDate as formatLocalDate } from '../utils/dateTime'

const severityOptions = ['Critical', 'High', 'Medium', 'Low']
const statusOptions = ['Open', 'Under Review', 'Resolved']

const initialForm = {
  title: '',
  investigation: '',
  category: 'Document Anomaly',
  severity: 'Medium',
  status: 'Open',
  description: '',
  evidence: '',
}

function SeverityBadge({ severity }) {
  return (
    <span className={`finding-severity severity-${severity.toLowerCase()}`}>
      <span />
      {severity}
    </span>
  )
}


function formatDate(date) {
  return formatLocalDate(date)
}

export default function FindingsPage() {
  const [findings, setFindings] = useState([])
  const [search, setSearch] = useState('')
  const [severityFilter, setSeverityFilter] = useState('All')
  const [statusFilter, setStatusFilter] = useState('All')
  const [modalOpen, setModalOpen] = useState(false)
  const [selectedFinding, setSelectedFinding] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(initialForm)
  const [formError, setFormError] = useState('')
  const [apiError, setApiError] = useState('')

  useEffect(() => {
    let active = true

    async function loadFindings() {
      try {
        const records = await api.getInvestigations()
        const investigations = await Promise.all(
          records.map((record) => api.getInvestigation(record.id))
        )
        const loaded = investigations.flatMap((investigation) =>
          (investigation.findings || []).map((finding) => {
            const evidence = finding.evidence || []
            const documents = new Map(
              investigation.documents.map((document) => [
                String(document.id),
                document.filename,
              ])
            )
            const evidenceText = evidence.map((item) => {
              const filename = documents.get(String(item.document_id))
                || `Document ${item.document_id}`
              const coordinates = item.bbox
                ? `, region ${item.bbox.x0}, ${item.bbox.y0}`
                : ''
              return `${filename}, page ${item.page}${coordinates}${item.value ? `: ${item.value}` : ''}`
            }).join('; ')

            return {
              id: String(finding.id),
              title: finding.title,
              investigation: investigation.title,
              category: (finding.anomaly_type || 'finding').replaceAll('_', ' '),
              severity: finding.severity === 'info'
                ? 'Low'
                : `${finding.severity || 'low'}`.replace(/^./, (letter) => letter.toUpperCase()),
              status: 'Under Review',
              description: finding.explanation || '',
              evidence: evidenceText,
              evidenceItems: evidence,
              classification: finding.classification,
              observationStatus: finding.observation_status,
              priorityScore: finding.priority_score,
              createdAt: finding.created_at,
              backend: true,
            }
          })
        )
        if (active) {
          setFindings(loaded)
        }
      } catch (error) {
        if (active) setApiError(error.message)
      }
    }

    loadFindings()
    return () => {
      active = false
    }
  }, [])

  const stats = useMemo(() => ({
    total: findings.length,
    critical: findings.filter(item => item.severity === 'Critical').length,
    high: findings.filter(item => item.severity === 'High').length,
    medium: findings.filter(item => item.severity === 'Medium').length,
    low: findings.filter(item => item.severity === 'Low').length,
  }), [findings])

  const filteredFindings = useMemo(() => {
    return findings.filter(item => {
      const query = search.toLowerCase()

      const matchesSearch =
        item.title.toLowerCase().includes(query) ||
        item.id.toLowerCase().includes(query) ||
        item.investigation.toLowerCase().includes(query)

      const matchesSeverity =
        severityFilter === 'All' || item.severity === severityFilter

      const matchesStatus =
        statusFilter === 'All' || item.status === statusFilter

      return matchesSearch && matchesSeverity && matchesStatus
    })
  }, [findings, search, severityFilter, statusFilter])

  const openCreateModal = () => {
    setForm(initialForm)
    setEditingId(null)
    setFormError('')
    setModalOpen(true)
  }

  const openEditModal = (finding) => {
    setForm({
      title: finding.title,
      investigation: finding.investigation,
      category: finding.category,
      severity: finding.severity,
      status: finding.status,
      description: finding.description,
      evidence: finding.evidence,
    })
    setEditingId(finding.id)
    setFormError('')
    setSelectedFinding(null)
    setModalOpen(true)
  }

  const closeModal = () => {
    setModalOpen(false)
    setForm(initialForm)
    setEditingId(null)
    setFormError('')
  }

  const handleSubmit = (event) => {
    event.preventDefault()

    if (!form.title.trim() || !form.description.trim()) {
      setFormError('Please enter a title and description.')
      return
    }

    if (editingId) {
      setFindings(current =>
        current.map(item =>
          item.id === editingId
            ? { ...item, ...form, updatedAt: new Date().toISOString() }
            : item
        )
      )
    } else {
      const newFinding = {
        ...form,
        id: `FND-${Date.now().toString().slice(-7)}`,
        createdAt: new Date().toISOString(),
      }

      setFindings(current => [newFinding, ...current])
    }

    closeModal()
  }

  const deleteFinding = (id) => {
    const confirmed = window.confirm(
      'Are you sure you want to delete this finding?'
    )

    if (!confirmed) return

    setFindings(current => current.filter(item => item.id !== id))
    setSelectedFinding(null)
  }

  const updateStatus = (id, status) => {
    setFindings(current =>
      current.map(item =>
        item.id === id ? { ...item, status } : item
      )
    )

    setSelectedFinding(current =>
      current?.id === id ? { ...current, status } : current
    )
  }

  if (selectedFinding) {
    const currentFinding =
      findings.find(item => item.id === selectedFinding.id) || selectedFinding

    return (
      <div className="findings-page">
        <button
          className="finding-back-btn"
          onClick={() => setSelectedFinding(null)}
        >
          <ArrowLeft size={17} />
          Back to Findings
        </button>

        <div className="finding-detail-header">
          <div>
            <span className="page-eyebrow">FINDING DETAILS</span>
            <h1>{currentFinding.title}</h1>
            <p>{currentFinding.id} · {currentFinding.category}</p>
          </div>

          <div className="finding-detail-actions">
            {!currentFinding.backend && (
              <>
                <button
                  className="finding-outline-btn"
                  onClick={() => openEditModal(currentFinding)}
                >
                  <Pencil size={16} /> Edit
                </button>
                <button
                  className="finding-delete-btn"
                  onClick={() => deleteFinding(currentFinding.id)}
                >
                  <Trash2 size={16} /> Delete
                </button>
              </>
            )}
          </div>
        </div>

        <div className="finding-detail-grid">
          <section className="finding-detail-panel">
            <div className="finding-panel-heading">
              <h3>Finding Overview</h3>
              <FileSearch size={20} />
            </div>

            <div className="finding-detail-body">
              <div className="finding-detail-field">
                <span>Description</span>
                <p>{currentFinding.description}</p>
              </div>

              <div className="finding-detail-field">
                <span>Evidence Reference</span>
                <p>{currentFinding.evidence || 'No evidence reference added.'}</p>
              </div>

              <div className="finding-detail-field">
                <span>Associated Investigation</span>
                <p>{currentFinding.investigation || 'Not associated'}</p>
              </div>

              <div className="finding-detail-field">
                <span>Category</span>
                <p>{currentFinding.category}</p>
              </div>
            </div>
          </section>

          <section className="finding-detail-panel">
            <div className="finding-panel-heading">
              <h3>Classification</h3>
              <ShieldAlert size={20} />
            </div>

            <div className="finding-detail-body">
              <div className="finding-detail-field">
                <span>Severity</span>
                <p><SeverityBadge severity={currentFinding.severity} /></p>
              </div>

              <div className="finding-detail-field">
                <span>Created On</span>
                <p>{formatDate(currentFinding.createdAt)}</p>
              </div>

              <div className="finding-detail-field">
                <span>Finding Status</span>
                <select
                  className="finding-select"
                  value={currentFinding.status}
                  disabled={currentFinding.backend}
                  onChange={event =>
                    updateStatus(currentFinding.id, event.target.value)
                  }
                >
                  {statusOptions.map(status => (
                    <option key={status}>{status}</option>
                  ))}
                </select>
              </div>
            </div>
          </section>
        </div>

        {modalOpen && (
          <FindingModal
            form={form}
            setForm={setForm}
            formError={formError}
            onSubmit={handleSubmit}
            onClose={closeModal}
            editing={Boolean(editingId)}
          />
        )}
      </div>
    )
  }

  return (
    <div className="findings-page">
      <div className="findings-header">
        <div>
          <span className="page-eyebrow">INVESTIGATION WORKSPACE</span>
          <h1>Findings</h1>
          <p>Record, review and manage findings from your investigations.</p>
        </div>

        {apiError && <section className="upload-errors" role="alert">{apiError}</section>}

        <button className="finding-primary-btn" onClick={openCreateModal}>
          <Plus size={18} />
          Create Finding
        </button>
      </div>

      <div className="findings-stats">
        <StatCard icon={FileSearch} label="Total Findings" value={stats.total} color="teal" />
        <StatCard icon={AlertTriangle} label="Critical" value={stats.critical} color="coral" />
        <StatCard icon={ShieldAlert} label="High Severity" value={stats.high} color="amber" />
        <StatCard icon={Clock3} label="Medium Severity" value={stats.medium} color="purple" />
      </div>

      <div className="findings-toolbar">
        <div className="findings-search">
          <Search size={18} />
          <input
            value={search}
            onChange={event => setSearch(event.target.value)}
            placeholder="Search findings by title, ID or investigation..."
          />
          {search && (
            <button onClick={() => setSearch('')} aria-label="Clear search">
              <X size={16} />
            </button>
          )}
        </div>

        <div className="finding-filter">
          <Filter size={16} />
          <select
            value={severityFilter}
            onChange={event => setSeverityFilter(event.target.value)}
          >
            <option value="All">All Severities</option>
            {severityOptions.map(item => <option key={item}>{item}</option>)}
          </select>
        </div>

        <div className="finding-filter">
          <select
            value={statusFilter}
            onChange={event => setStatusFilter(event.target.value)}
          >
            <option value="All">All Statuses</option>
            {statusOptions.map(item => <option key={item}>{item}</option>)}
          </select>
        </div>
      </div>

      <section className="findings-table-panel">
        <div className="findings-table-heading">
          <div>
            <h3>All Findings</h3>
            <p>Review and manage recorded findings.</p>
          </div>
          <span>{filteredFindings.length} records</span>
        </div>

        {filteredFindings.length === 0 ? (
          <div className="findings-empty">
            <div className="findings-empty-icon"><FileSearch size={32} /></div>
            <h3>{findings.length === 0 ? 'No findings recorded yet' : 'No matching findings'}</h3>
            <p>
              {findings.length === 0
                ? 'Create a finding to document an anomaly, observation or issue discovered during an investigation.'
                : 'Try changing your search or filters.'}
            </p>
            {findings.length === 0 && !apiError && (
              <button className="finding-primary-btn" onClick={openCreateModal}>
                <Plus size={17} /> Create First Finding
              </button>
            )}
          </div>
        ) : (
          <div className="findings-table-scroll">
            <table className="findings-table">
              <thead>
                <tr>
                  <th>FINDING</th>
                  <th>INVESTIGATION</th>
                  <th>CATEGORY</th>
                  <th>SEVERITY</th>
                  <th>STATUS</th>
                  <th>DATE</th>
                  <th>ACTION</th>
                </tr>
              </thead>
              <tbody>
                {filteredFindings.map(item => (
                  <tr key={item.id}>
                    <td>
                      <div className="finding-name-cell">
                        <strong>{item.title}</strong>
                        <span>{item.id}</span>
                      </div>
                    </td>
                    <td>{item.investigation || '—'}</td>
                    <td>{item.category}</td>
                    <td><SeverityBadge severity={item.severity} /></td>
                    <td>
  <StatusPill status={item.status} variant="finding" />
</td>
                    <td>{formatDate(item.createdAt)}</td>
                    <td>
                      <div className="finding-row-actions">
                        <button
                          title="View details"
                          onClick={() => setSelectedFinding(item)}
                        >
                          <Eye size={16} />
                        </button>
                        {!item.backend && (
                          <>
                            <button
                              title="Edit finding"
                              onClick={() => openEditModal(item)}
                            >
                              <Pencil size={16} />
                            </button>
                            <button
                              title="Delete finding"
                              onClick={() => deleteFinding(item.id)}
                            >
                              <Trash2 size={16} />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {modalOpen && (
        <FindingModal
          form={form}
          setForm={setForm}
          formError={formError}
          onSubmit={handleSubmit}
          onClose={closeModal}
          editing={Boolean(editingId)}
        />
      )}
    </div>
  )
}

function StatCard({ icon: Icon, label, value, color }) {
  return (
    <div className="finding-stat-card">
      <div className={`finding-stat-icon ${color}`}><Icon size={21} /></div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </div>
  )
}

function FindingModal({ form, setForm, formError, onSubmit, onClose, editing }) {
  const update = (field, value) => {
    setForm(current => ({ ...current, [field]: value }))
  }

  return (
    <div className="finding-modal-overlay" onMouseDown={event => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <form className="finding-modal" onSubmit={onSubmit}>
        <div className="finding-modal-header">
          <div>
            <h2>{editing ? 'Edit Finding' : 'Create New Finding'}</h2>
            <p>Enter the details of the finding below.</p>
          </div>
          <button type="button" className="finding-modal-close" onClick={onClose}>
            <X size={19} />
          </button>
        </div>

        <div className="finding-form-group">
          <label>Finding Title *</label>
          <input
            value={form.title}
            onChange={event => update('title', event.target.value)}
            placeholder="e.g. Inconsistent financial records"
            maxLength={120}
          />
        </div>

        <div className="finding-form-group">
          <label>Investigation Name / ID</label>
          <input
            value={form.investigation}
            onChange={event => update('investigation', event.target.value)}
            placeholder="Enter investigation name or ID"
          />
        </div>

        <div className="finding-form-row">
          <div className="finding-form-group">
            <label>Category</label>
            <select value={form.category} onChange={event => update('category', event.target.value)}>
              <option>Document Anomaly</option>
              <option>Data Inconsistency</option>
              <option>Financial Irregularity</option>
              <option>Identity Mismatch</option>
              <option>Suspicious Activity</option>
              <option>Other</option>
            </select>
          </div>

          <div className="finding-form-group">
            <label>Severity</label>
            <select value={form.severity} onChange={event => update('severity', event.target.value)}>
              {severityOptions.map(item => <option key={item}>{item}</option>)}
            </select>
          </div>
        </div>

        <div className="finding-form-group">
          <label>Status</label>
          <select value={form.status} onChange={event => update('status', event.target.value)}>
            {statusOptions.map(item => <option key={item}>{item}</option>)}
          </select>
        </div>

        <div className="finding-form-group">
          <label>Description *</label>
          <textarea
            value={form.description}
            onChange={event => update('description', event.target.value)}
            placeholder="Describe the finding and why it matters..."
            rows={4}
          />
        </div>

        <div className="finding-form-group">
          <label>Evidence Reference (Optional)</label>
          <input
            value={form.evidence}
            onChange={event => update('evidence', event.target.value)}
            placeholder="Document name, page number or reference"
          />
        </div>

        {formError && <p className="finding-form-error">{formError}</p>}

        <div className="finding-modal-actions">
          <button type="button" className="finding-cancel-btn" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="finding-primary-btn">
            <Plus size={16} />
            {editing ? 'Save Changes' : 'Create Finding'}
          </button>
        </div>
      </form>
    </div>
  )
}
