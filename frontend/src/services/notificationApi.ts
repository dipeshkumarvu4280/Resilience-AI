import api from './api';
import type {
  NotificationUserView,
  NotificationPreference,
  NotificationPreferenceUpdate,
  ChannelStatusResponse,
  NotificationCategory,
  NotificationSeverity,
} from '../types';

export const notificationApi = {
  /**
   * Fetch user-scoped notifications with optional filters and pagination.
   */
  async getNotifications(params?: {
    category?: NotificationCategory;
    severity?: NotificationSeverity;
    unread_only?: boolean;
    limit?: number;
    skip?: number;
  }): Promise<NotificationUserView[]> {
    const response = await api.get<NotificationUserView[]>('/notifications', { params });
    return response.data;
  },

  /**
   * Fetch unread in-app notification count for the current user.
   */
  async getUnreadCount(): Promise<number> {
    const response = await api.get<{ unread_count: number }>('/notifications/unread-count');
    return response.data.unread_count;
  },

  /**
   * Fetch status of delivery channels (In-App, WhatsApp).
   */
  async getChannelStatus(): Promise<ChannelStatusResponse> {
    const response = await api.get<ChannelStatusResponse>('/notifications/channels/status');
    return response.data;
  },

  /**
   * Fetch user notification preferences.
   */
  async getPreferences(): Promise<NotificationPreference> {
    const response = await api.get<NotificationPreference>('/notifications/preferences');
    return response.data;
  },

  /**
   * Update user notification preferences.
   */
  async updatePreferences(updateData: NotificationPreferenceUpdate): Promise<NotificationPreference> {
    const response = await api.put<NotificationPreference>('/notifications/preferences', updateData);
    return response.data;
  },

  /**
   * Mark a single notification as read.
   */
  async markAsRead(notificationId: string): Promise<boolean> {
    const response = await api.post<{ success: boolean }>(`/notifications/${notificationId}/read`);
    return response.data.success;
  },

  /**
   * Mark all unread notifications as read.
   */
  async markAllAsRead(): Promise<number> {
    const response = await api.post<{ success: boolean; count: number }>('/notifications/read-all');
    return response.data.count;
  },

  /**
   * Fetch single notification by ID.
   */
  async getNotificationById(notificationId: string): Promise<NotificationUserView> {
    const response = await api.get<NotificationUserView>(`/notifications/${notificationId}`);
    return response.data;
  },
};

export default notificationApi;
