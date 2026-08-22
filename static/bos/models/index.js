/**
 * Zintriq universal object model (Phase 3 platform foundation).
 * @module bos/models
 */

/** @typedef {Object} PlatformObject
 * @property {string} id
 * @property {string} status
 * @property {string} [createdAt]
 * @property {string} [updatedAt]
 * @property {string[]} [tagIds]
 */

/** @typedef {Object} Activity
 * @property {string} id
 * @property {string} action
 * @property {string} message
 * @property {string} actor
 * @property {string} entityType
 * @property {string} entityId
 * @property {string} at
 */

/** @typedef {Object} Note
 * @property {string} id
 * @property {string} entityType
 * @property {string} entityId
 * @property {string} body
 * @property {string} author
 * @property {string} [createdAt]
 * @property {string} [updatedAt]
 */

/** @typedef {Object} Attachment
 * @property {string} id
 * @property {string} entityType
 * @property {string} entityId
 * @property {string} name
 * @property {'image'|'pdf'|'doc'|'other'} type
 * @property {string} size
 * @property {string} [mime]
 * @property {string} [url]
 */

/** @typedef {Object} Notification
 * @property {string} id
 * @property {string} title
 * @property {string} body
 * @property {'info'|'success'|'warning'|'error'} priority
 * @property {boolean} read
 * @property {string} [entityType]
 * @property {string} [entityId]
 * @property {string} [href]
 */

export {};
