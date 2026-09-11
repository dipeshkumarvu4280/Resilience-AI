import React, { useState, useEffect } from 'react';
import {
  X,
  Gauge,
  Send,
  Play,
  Square,
  Activity,
  AlertTriangle,
  CheckCircle,
  TrendingUp,
  TrendingDown,
  Shuffle,
  Clock,
  Radio,
} from 'lucide-react';
import {
  sendSensorReading,
  startLiveStream,
  stopLiveStream,
  getLiveStreamStatus,
} from '../../services/api';
import type { Sensor, LiveStreamSession, SimulationTrend } from '../../types';

interface SensorReadingModalProps {
  isOpen: boolean;
  sensor: Sensor | null;
  onClose: () => void;
  onReadingSubmitted?: () => void;
}

export const SensorReadingModal: React.FC<SensorReadingModalProps> = ({
  isOpen,
  sensor,
  onClose,
  onReadingSubmitted,
}) => {
  const [activeTab, setActiveTab] = useState<'manual' | 'stream'>('manual');

  // Manual Input State
  const [manualValue, setManualValue] = useState<number | ''>('');
  const [manualLoading, setManualLoading] = useState(false);
  const [manualResult, setManualResult] = useState<{
    transition_type: string;
    is_breach: boolean;
    reading_value: number;
  } | null>(null);

  // Auto-Stream State
  const [startingValue, setStartingValue] = useState<number | ''>('');
  const [minValue, setMinValue] = useState<number | ''>('');
  const [maxValue, setMaxValue] = useState<number | ''>('');
  const [intervalSeconds, setIntervalSeconds] = useState<number>(5);
  const [trend, setTrend] = useState<SimulationTrend>('RISING');
  const [stepSize, setStepSize] = useState<number | ''>('');

  const [streamSession, setStreamSession] = useState<LiveStreamSession | null>(null);
  const [streamLoading, setStreamLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          onClose();
        }
      };
      window.addEventListener('keydown', handleKeyDown);
      return () => {
        document.body.style.overflow = '';
        window.removeEventListener('keydown', handleKeyDown);
      };
    }
  }, [isOpen, onClose]);

  useEffect(() => {
    if (sensor) {
      const initVal = sensor.current_reading !== null && sensor.current_reading !== undefined
        ? sensor.current_reading
        : sensor.threshold * 0.8;
      setManualValue(initVal);
      setStartingValue(initVal);
      setMinValue(Math.max(0, sensor.threshold * 0.5));
      setMaxValue(sensor.threshold * 1.6);
      setStepSize(parseFloat(((sensor.threshold * 0.1) || 0.2).toFixed(2)));
      setManualResult(null);
      setError(null);

      // Check stream status
      getLiveStreamStatus(sensor.sensor_id)
        .then((res) => {
          if (res.is_streaming && res.session) {
            setStreamSession(res.session);
          } else {
            setStreamSession(null);
          }
        })
        .catch(() => {});
    }
  }, [sensor]);

  if (!isOpen || !sensor) return null;

  const isInactive = sensor.status !== 'ACTIVE';

  const handleSendManualReading = async (e: React.FormEvent) => {
    e.preventDefault();
    if (manualValue === '' || isNaN(Number(manualValue))) {
      setError('Please enter a valid numeric reading.');
      return;
    }

    setManualLoading(true);
    setError(null);
    try {
      const res = await sendSensorReading(sensor.sensor_id, {
        value: Number(manualValue),
      });

      setManualResult({
        transition_type: res.transition_type,
        is_breach: res.is_breach,
        reading_value: res.reading.value,
      });

      if (onReadingSubmitted) onReadingSubmitted();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to submit sensor reading.');
    } finally {
      setManualLoading(false);
    }
  };

  const handleStartStream = async (e: React.FormEvent) => {
    e.preventDefault();
    if (startingValue === '' || minValue === '' || maxValue === '') {
      setError('Please fill in all numerical boundary fields.');
      return;
    }
    if (Number(minValue) >= Number(maxValue)) {
      setError('Minimum value must be less than Maximum value.');
      return;
    }

    setStreamLoading(true);
    setError(null);
    try {
      const session = await startLiveStream(sensor.sensor_id, {
        starting_value: Number(startingValue),
        min_value: Number(minValue),
        max_value: Number(maxValue),
        interval_seconds: Number(intervalSeconds),
        trend,
        step_size: stepSize !== '' ? Number(stepSize) : undefined,
      });

      setStreamSession(session);
      if (onReadingSubmitted) onReadingSubmitted();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to start live stream.');
    } finally {
      setStreamLoading(false);
    }
  };

  const handleStopStream = async () => {
    setStreamLoading(true);
    setError(null);
    try {
      await stopLiveStream(sensor.sensor_id);
      setStreamSession(null);
      if (onReadingSubmitted) onReadingSubmitted();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to stop live stream.');
    } finally {
      setStreamLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-3 sm:p-4 md:p-6"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="reading-modal-title"
    >
      <div className="relative w-full max-w-xl rounded-2xl bg-white shadow-2xl border border-slate-200 flex flex-col max-h-[calc(100vh-1.5rem)] sm:max-h-[calc(100vh-2.5rem)] overflow-hidden">
        {/* Pinned Header (shrink-0) */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50/90 shrink-0 z-10">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-cyan-100 text-cyan-700 flex items-center justify-center font-bold shrink-0">
              <Radio className="w-5 h-5" />
            </div>
            <div>
              <h3 id="reading-modal-title" className="text-base font-bold text-slate-900">{sensor.name}</h3>
              <p className="text-xs text-slate-500">
                {sensor.sensor_type} • {sensor.location_name} • Threshold: <strong className="text-slate-800">{sensor.threshold} {sensor.unit}</strong>
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-200/60 hover:text-slate-700 transition cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Warning if sensor not ACTIVE */}
        {isInactive && (
          <div className="mx-6 mt-4 p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-center gap-2 shrink-0">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
            <span>
              Sensor is currently in <strong>{sensor.status}</strong> state. It must be <strong>ACTIVE</strong> to submit readings or start streams.
            </span>
          </div>
        )}

        {/* Error Alert */}
        {error && (
          <div className="mx-6 mt-4 p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-800 text-xs flex items-center gap-2 shrink-0">
            <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Mode Tabs */}
        <div className="flex border-b border-slate-200 px-6 pt-3 gap-6 bg-slate-50/40 shrink-0">
          <button
            onClick={() => setActiveTab('manual')}
            className={`pb-3 text-xs font-bold transition flex items-center gap-2 border-b-2 cursor-pointer ${
              activeTab === 'manual'
                ? 'border-cyan-600 text-cyan-800'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Gauge className="w-4 h-4" />
            Manual Telemetry Input
          </button>
          <button
            onClick={() => setActiveTab('stream')}
            className={`pb-3 text-xs font-bold transition flex items-center gap-2 border-b-2 cursor-pointer ${
              activeTab === 'stream'
                ? 'border-cyan-600 text-cyan-800'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Activity className="w-4 h-4" />
            Auto-Stream Simulation {streamSession && <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />}
          </button>
        </div>

        {/* Tab Content (Scrollable) */}
        <div className="p-6 flex-1 overflow-y-auto min-h-0">
          {activeTab === 'manual' && (
            <form onSubmit={handleSendManualReading} className="space-y-4">
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 flex items-center justify-between">
                <div>
                  <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Current Reading</div>
                  <div className="text-xl font-black text-slate-900">
                    {sensor.current_reading !== null && sensor.current_reading !== undefined
                      ? `${sensor.current_reading} ${sensor.unit}`
                      : 'No readings recorded'}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Alert Threshold</div>
                  <div className="text-sm font-bold text-red-600">
                    &gt; {sensor.threshold} {sensor.unit}
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  New Reading Value ({sensor.unit}) *
                </label>
                <div className="relative">
                  <input
                    type="number"
                    step="0.01"
                    required
                    disabled={isInactive || manualLoading}
                    value={manualValue}
                    onChange={(e) => setManualValue(e.target.value === '' ? '' : parseFloat(e.target.value))}
                    placeholder={`Enter value in ${sensor.unit}`}
                    className="w-full rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-bold text-slate-900 focus:border-cyan-600 focus:outline-hidden focus:ring-1 focus:ring-cyan-600 disabled:bg-slate-100"
                  />
                  <div className="absolute right-3 top-2.5 text-xs font-bold text-slate-400">
                    {sensor.unit}
                  </div>
                </div>
                {Number(manualValue) > sensor.threshold ? (
                  <p className="text-[11px] font-bold text-red-600 mt-1.5 flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    Value exceeds threshold ({sensor.threshold} {sensor.unit}) $\rightarrow$ Will trigger Threshold Breach Alert.
                  </p>
                ) : (
                  <p className="text-[11px] text-slate-500 mt-1.5 flex items-center gap-1.5">
                    <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                    Value is within normal operational bounds.
                  </p>
                )}
              </div>

              {/* Result Banner */}
              {manualResult && (
                <div
                  className={`p-3 rounded-xl border text-xs flex items-center gap-2 ${
                    manualResult.is_breach
                      ? 'bg-red-50 border-red-200 text-red-900 font-medium'
                      : 'bg-emerald-50 border-emerald-200 text-emerald-900 font-medium'
                  }`}
                >
                  {manualResult.is_breach ? (
                    <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
                  ) : (
                    <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0" />
                  )}
                  <div>
                    Reading <strong>{manualResult.reading_value} {sensor.unit}</strong> recorded. State transition: <strong>{manualResult.transition_type}</strong>.
                  </div>
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-100 transition"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={isInactive || manualLoading}
                  className="px-5 py-2.5 rounded-xl bg-cyan-700 hover:bg-cyan-800 text-white text-xs font-bold shadow-sm transition flex items-center gap-2 disabled:opacity-50"
                >
                  <Send className="w-3.5 h-3.5" />
                  {manualLoading ? 'Sending...' : 'Send Live Reading'}
                </button>
              </div>
            </form>
          )}

          {activeTab === 'stream' && (
            <div>
              {streamSession ? (
                <div className="space-y-4">
                  <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-950 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-3 h-3 rounded-full bg-emerald-500 animate-ping" />
                      <div>
                        <div className="text-xs font-bold">Auto-Simulation Stream Active</div>
                        <div className="text-[11px] text-emerald-700">
                          Session: {streamSession.session_id} • Trend: {streamSession.configuration?.trend} • Interval: {streamSession.configuration?.interval_seconds}s
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs font-bold text-emerald-900">Emitted Readings</div>
                      <div className="text-lg font-black text-emerald-800">{streamSession.readings_emitted}</div>
                    </div>
                  </div>

                  <p className="text-xs text-slate-500">
                    The background generator is dynamically emitting runtime telemetry into the intelligence pipeline.
                  </p>

                  <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
                    <button
                      type="button"
                      onClick={onClose}
                      className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-100 transition"
                    >
                      Close
                    </button>
                    <button
                      type="button"
                      onClick={handleStopStream}
                      disabled={streamLoading}
                      className="px-5 py-2.5 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-bold shadow-sm transition flex items-center gap-2 disabled:opacity-50"
                    >
                      <Square className="w-3.5 h-3.5" />
                      {streamLoading ? 'Halting...' : 'Stop Live Stream'}
                    </button>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleStartStream} className="space-y-4">
                  <p className="text-xs text-slate-600 leading-relaxed">
                    Configure dynamic IoT telemetry generator. Readings are generated in real-time according to your parameters.
                  </p>

                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <label className="block text-[11px] font-bold text-slate-700 mb-1">Starting Value *</label>
                      <input
                        type="number"
                        step="0.1"
                        required
                        disabled={isInactive}
                        value={startingValue}
                        onChange={(e) => setStartingValue(e.target.value === '' ? '' : parseFloat(e.target.value))}
                        className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-slate-900 focus:border-cyan-600 focus:outline-hidden"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-slate-700 mb-1">Min Value *</label>
                      <input
                        type="number"
                        step="0.1"
                        required
                        disabled={isInactive}
                        value={minValue}
                        onChange={(e) => setMinValue(e.target.value === '' ? '' : parseFloat(e.target.value))}
                        className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-slate-900 focus:border-cyan-600 focus:outline-hidden"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-slate-700 mb-1">Max Value *</label>
                      <input
                        type="number"
                        step="0.1"
                        required
                        disabled={isInactive}
                        value={maxValue}
                        onChange={(e) => setMaxValue(e.target.value === '' ? '' : parseFloat(e.target.value))}
                        className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-slate-900 focus:border-cyan-600 focus:outline-hidden"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] font-bold text-slate-700 mb-1">Interval (Seconds)</label>
                      <div className="relative">
                        <Clock className="absolute left-3 top-2.5 w-3.5 h-3.5 text-slate-400" />
                        <input
                          type="number"
                          min="1"
                          max="60"
                          required
                          disabled={isInactive}
                          value={intervalSeconds}
                          onChange={(e) => setIntervalSeconds(parseInt(e.target.value) || 5)}
                          className="w-full rounded-xl border border-slate-200 pl-8 pr-3 py-2 text-xs font-bold text-slate-900 focus:border-cyan-600 focus:outline-hidden"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-slate-700 mb-1">Step Delta ({sensor.unit})</label>
                      <input
                        type="number"
                        step="0.01"
                        disabled={isInactive}
                        value={stepSize}
                        onChange={(e) => setStepSize(e.target.value === '' ? '' : parseFloat(e.target.value))}
                        placeholder="Default: 5% delta"
                        className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-900 focus:border-cyan-600 focus:outline-hidden"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider mb-2">
                      Simulation Trajectory Trend
                    </label>
                    <div className="grid grid-cols-3 gap-2">
                      <button
                        type="button"
                        onClick={() => setTrend('RISING')}
                        disabled={isInactive}
                        className={`flex items-center justify-center gap-2 p-2.5 rounded-xl border text-xs font-bold transition ${
                          trend === 'RISING'
                            ? 'border-red-500 bg-red-50 text-red-950 ring-1 ring-red-500'
                            : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                        }`}
                      >
                        <TrendingUp className="w-4 h-4 text-red-600" />
                        RISING
                      </button>
                      <button
                        type="button"
                        onClick={() => setTrend('FALLING')}
                        disabled={isInactive}
                        className={`flex items-center justify-center gap-2 p-2.5 rounded-xl border text-xs font-bold transition ${
                          trend === 'FALLING'
                            ? 'border-emerald-500 bg-emerald-50 text-emerald-950 ring-1 ring-emerald-500'
                            : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                        }`}
                      >
                        <TrendingDown className="w-4 h-4 text-emerald-600" />
                        FALLING
                      </button>
                      <button
                        type="button"
                        onClick={() => setTrend('FLUCTUATING')}
                        disabled={isInactive}
                        className={`flex items-center justify-center gap-2 p-2.5 rounded-xl border text-xs font-bold transition ${
                          trend === 'FLUCTUATING'
                            ? 'border-cyan-500 bg-cyan-50 text-cyan-950 ring-1 ring-cyan-500'
                            : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                        }`}
                      >
                        <Shuffle className="w-4 h-4 text-cyan-600" />
                        FLUCTUATING
                      </button>
                    </div>
                  </div>

                  <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
                    <button
                      type="button"
                      onClick={onClose}
                      className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-100 transition"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isInactive || streamLoading}
                      className="px-5 py-2.5 rounded-xl bg-cyan-700 hover:bg-cyan-800 text-white text-xs font-bold shadow-sm transition flex items-center gap-2 disabled:opacity-50"
                    >
                      <Play className="w-3.5 h-3.5" />
                      {streamLoading ? 'Starting...' : 'Start Live Stream'}
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
export default SensorReadingModal;
