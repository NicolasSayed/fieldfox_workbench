function test_full_session(root)
% Synthetic cross-language checks; no hardware or proprietary recordings.
repo = fileparts(fileparts(fileparts(mfilename('fullpath'))));
addpath(fullfile(repo,'matlab'));
cases = {'multi','rtsa','old','zero','short_index','short_next','partial','short_explicit','empty','header','deviated'};
for c = 1:numel(cases)
    name = cases{c}; source = fullfile(root,['session_' name]);
    target = fullfile(root,['native_' name]);
    chunk=2; options={};
    if c>4, chunk=250; end
    if strcmp(name,'short_explicit'), options={'ExpectedSweeps',500}; end
    if strcmp(name,'empty'), options={'ExpectedSweeps',3}; end
    result = export_fieldfox_session(source,target,'SweepsPerPart',chunk,options{:});
    expectedRoot = fullfile(root,['python_' name]);
    expected = jsondecode(fileread(fullfile(expectedRoot,'manifest.json')));
    actual = jsondecode(fileread(fullfile(target,'manifest.json')));
    assert(actual.complete && numel(actual.parts)==numel(expected.parts));
    assert(numel(result.parts)==numel(expected.parts));
    for k = 1:numel(actual.parts)
        a = load(fullfile(target,actual.parts(k).file));
        e = load(fullfile(expectedRoot,expected.parts(k).file));
        fields = {'power_dbm_traces','timestamp_ticks','timestamp_ticks_utc', ...
            'sweep_indices','trace_slot_indices','state_ids','trace_masks', ...
            'auxiliary_values','elapsed_s','timestamp_utc','timestamp_est', ...
            'zero_filled','timestamp_valid','recorded_value_counts','recovery_fill_dbm'};
        for j = 1:numel(fields)
            assert(isequaln(a.(fields{j}),e.(fields{j})),['Mismatch: ' name ' / ' fields{j}]);
        end
        axis = char(a.axis_kind);
        assert(max(abs(a.(axis)-e.(axis)),[],'all')<1e-6);
        assert(actual.parts(k).start_sweep==expected.parts(k).start_sweep);
        assert(actual.parts(k).stop_sweep==expected.parts(k).stop_sweep);
        partial = matfile(fullfile(target,actual.parts(k).file));
        assert(isequal(partial.power_dbm_traces(1,1,1),e.power_dbm_traces(1,1,1)));
    end
    % Existing exports and original session directories are protected.
    must_fail(@() export_fieldfox_session(source,target));
    must_fail(@() export_fieldfox_session(source,fullfile(source,'bad_export')));
end
badTarget = fullfile(root,'bad_output');
before = dir(root);
must_fail(@() export_fieldfox_session(fullfile(root,'session_bad'),badTarget,'SweepsPerPart',1));
assert(~isfolder(badTarget)); after = dir(root);
assert(isequal({before.name},{after.name}),'Failed export left temporary folders.');
fprintf('PASS: 11 synthetic sessions; all slots, parts, clocks, axes, v7.3 partial reads, 500/497 recovery, protection and failure cleanup.\n');
end

function must_fail(work)
failed = false;
try, work(); catch, failed = true; end
assert(failed,'Expected rejection.');
end
