
import { X, Clock, FileText, Plus, Pencil, Trash2 } from 'lucide-react'

const icons = {
  created: Plus,
  updated: Pencil,
  deleted: Trash2,
  document: FileText,
}

export default function AuditTrailModal({
  isOpen,
  onClose,
  events = [],
  title = 'Audit Trail',
}) {
  if (!isOpen) return null

  return (
    <div
      className="audit-modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose?.()
      }}
    >
      <section className="audit-modal">
        <header className="audit-modal-header">
          <div>
            <h2>{title}</h2>
            <p>{events.length} recorded events</p>
          </div>
          <button onClick={onClose} aria-label="Close audit trail">
            <X size={20} />
          </button>
        </header>

        <div className="audit-modal-body">
          {events.length === 0 ? (
            <div className="audit-empty">
              <Clock size={30} />
              <h3>No activity recorded</h3>
              <p>Actions will appear here when audit events are recorded.</p>
            </div>
          ) : (
            <div className="audit-event-list">
              {events.map((event, index) => {
                const Icon = icons[event.type] || Clock

                return (
                  <article className="audit-event" key={event.id || index}>
                    <div className="audit-event-icon">
                      <Icon size={17} />
                    </div>
                    <div>
                      <strong>{event.action}</strong>
                      <p>{event.description}</p>
                      <span>
                        {event.actor || 'Unknown user'} ·{' '}
                        {event.timestamp
                          ? new Date(event.timestamp).toLocaleString('en-IN')
                          : 'Time unavailable'}
                      </span>
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
