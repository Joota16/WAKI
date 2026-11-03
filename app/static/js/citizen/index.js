import { initSummary } from './summary.js';
import { initSituations } from './situations.js';
import { initLocation } from './location.js';
import { initAttachments } from './attachments.js';
import { initReportModal } from './modal.js';
import { initSubmission } from './submission.js';
import { initReportPhone } from './phone.js';

initSummary();
initSituations();
initReportPhone();
initSubmission({ photos: initAttachments(), location: initLocation(), modal: initReportModal() });
