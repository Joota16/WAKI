import { initSummary } from './summary.js';
import { initLocation } from './location.js';
import { initAttachments } from './attachments.js';
import { initReportModal } from './modal.js';
import { initSubmission } from './submission.js';

initSummary();
initSubmission({ photos: initAttachments(), location: initLocation(), modal: initReportModal() });
