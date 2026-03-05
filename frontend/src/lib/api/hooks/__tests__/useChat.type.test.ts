import { describe, it, expect } from 'vitest';
import type { ToolExecutionResult, ToolCall } from '../useChat';

describe('ToolExecutionResult type', () => {
  it('ToolExecutionResult type is exported and structurally valid', () => {
    // Verify the type can be imported and satisfies the expected shape
    const successResult: ToolExecutionResult = {
      tool_name: 'run_engine',
      status: 'success',
      reason_code: 'ok',
      retryable: false,
      latency_ms: 250,
      result: { gdp_impact: 1.5 },
    };

    expect(successResult.status).toBe('success');
    expect(successResult.tool_name).toBe('run_engine');
    expect(successResult.retryable).toBe(false);
    expect(successResult.latency_ms).toBe(250);
  });

  it('ToolExecutionResult supports error status with error_summary', () => {
    const errorResult: ToolExecutionResult = {
      tool_name: 'run_engine',
      status: 'error',
      reason_code: 'engine_timeout',
      retryable: true,
      latency_ms: 5000,
      error_summary: 'Engine timed out after 5s',
    };

    expect(errorResult.status).toBe('error');
    expect(errorResult.error_summary).toBe('Engine timed out after 5s');
    expect(errorResult.retryable).toBe(true);
  });

  it('ToolExecutionResult supports blocked status', () => {
    const blockedResult: ToolExecutionResult = {
      tool_name: 'build_scenario',
      status: 'blocked',
      reason_code: 'governance_hold',
      retryable: false,
      latency_ms: 10,
    };

    expect(blockedResult.status).toBe('blocked');
    expect(blockedResult.reason_code).toBe('governance_hold');
  });

  it('ToolCall result field can hold a ToolExecutionResult-shaped value', () => {
    const tc: ToolCall = {
      tool_name: 'run_engine',
      arguments: { scenario_id: 'sc-01' },
      result: {
        status: 'success',
        reason_code: 'ok',
        retryable: false,
        latency_ms: 320,
        result: { gdp_impact: 1.5 },
      },
    };

    expect(tc.result).toBeDefined();
    expect((tc.result as Record<string, unknown>).status).toBe('success');
  });
});
