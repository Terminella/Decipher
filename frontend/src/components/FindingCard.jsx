
import { Eye, Pencil, CalendarDays } from 'lucide-react'
import StatusPill from './StatusPill'
import { formatDate } from '../utils/dateTime'

export default function FindingCard({
  finding,
  onView,
  onEdit,
}) {
  const severity = finding.severity?.toLowerCase() || 'medium'

  return (
    <article className="finding-card">
      <div className="finding-card-header">
        <div>
          <h3>{finding.title}</h3>
          <span>{finding.id}</span>
        </div>
        <span className={`finding-severity severity-${severity}`}>
          <span />
          {finding.severity}
        </span>
      </div>

      <p>{finding.description}</p>

      <div className="finding-card-meta">
        <span>{finding.category}</span>
        <span>{finding.investigation || 'No investigation'}</span>
      </div>

      <div className="finding-card-footer">
        <StatusPill status={finding.status} variant="finding" />

        <span>
          <CalendarDays size={14} />
          {finding.createdAt ? formatDate(finding.createdAt) : 'No date'}
        </span>
      </div>

      <div className="finding-card-actions">
        <button onClick={() => onView?.(finding)}>
          <Eye size={15} /> View
        </button>
        <button onClick={() => onEdit?.(finding)}>
          <Pencil size={15} /> Edit
        </button>
      </div>
    </article>
  )
}
