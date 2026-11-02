function manifest = export_fieldfox_session(sessionFolder, outputFolder, varargin)
%EXPORT_FIELDFOX_SESSION Export ALL sweeps, trace slots and bins in bounded parts.
% export_fieldfox_session(sessionFolder,outputFolder,'SweepsPerPart',5000)
% Power dimensions: sweep x trace slot x point. Indices are zero-based.
% Parts split at state changes. Output must be new and outside the input.
% Native MATLAB v7.3 files support partial access with matfile(). No Python.
% MaxPartMiB budgets array payload, NOT total process memory.
p = inputParser; p.PartialMatching = false;
addParameter(p,'SweepsPerPart',5000); addParameter(p,'MaxPartMiB',128);
addParameter(p,'SourceTimeZone','EST'); addParameter(p,'DSTFold',[]);
addParameter(p,'RecoverIncomplete',true); addParameter(p,'ExpectedSweeps',[]);
parse(p,varargin{:}); o = p.Results;
validateattributes(o.SweepsPerPart,{'numeric'},{'scalar','integer','positive','finite'});
validateattributes(o.MaxPartMiB,{'numeric'},{'scalar','positive','finite','<=',512});
source = char(java.io.File(char(sessionFolder)).getCanonicalPath());
target = char(java.io.File(char(outputFolder)).getCanonicalPath());
assert(~strcmpi(source,target) && ~startsWith(lower(target),lower([source filesep])), ...
    'fieldfox:output','Output must be outside the original session folder.');
assert(~isfolder(target) && ~isfile(target),'fieldfox:output','Output already exists.');
args = {'MaxSweeps',Inf,'SourceTimeZone',o.SourceTimeZone,'DSTFold',o.DSTFold, ...
    'RecoverIncomplete',o.RecoverIncomplete,'ExpectedSweeps',o.ExpectedSweeps,'WarnRecovery',false};
probe = read_fieldfox(source,'StopSweep',1,args{:});
metadata = jsondecode(probe.metadata_json); states = probe.states;
total = metadata.n_sweeps; slots = states(1).blocks; points = states(1).points;
if metadata.recovery.zero_filled_sweeps>0
    warning('fieldfox:recovered','Zero-filling %d incomplete/missing sweeps; timestamps for missing headers stay blank.',metadata.recovery.zero_filled_sweeps);
end
starts = [states.first_trace];
assert(starts(1)==0 && all(diff(starts)>0) && all(starts<total), ...
    'fieldfox:state','Invalid state transition boundaries.');
bytesPerRow = 4*(slots*points+states(1).auxiliary)+1024;
capacity = min([o.SweepsPerPart, floor(o.MaxPartMiB*1024^2/bytesPerRow), ...
    floor(20000000/max([points states(1).auxiliary 1])), total]);
assert(capacity>=1,'fieldfox:memory','Part budget is too small for one sweep.');
[parent,~,~] = fileparts(target);
if ~isfolder(parent), mkdir(parent); end
stage = tempname(parent);
assert(startsWith(lower(stage),lower([parent filesep])), 'fieldfox:output','Invalid staging path.');
mkdir(stage); cleanup = onCleanup(@() remove_stage(stage));
manifest = struct('schema_version',1,'complete',true,'source_session',source, ...
    'metadata',metadata,'source_timezone',char(o.SourceTimeZone),'dst_fold',o.DSTFold, ...
    'power_dimensions',{{'sweep','trace_slot','point'}},'index_base',0, ...
    'stop_sweep_exclusive',true,'parts',{{}});
ends = [starts(2:end) total]; partNumber = 0;
for stateIndex = 1:numel(states)
    for first = starts(stateIndex):capacity:ends(stateIndex)-1
        stop = min(first+capacity,ends(stateIndex)); rows = stop-first;
        data = read_fieldfox(source,'StartSweep',first,'StopSweep',stop,args{:});
        assert(all(data.state_ids==states(stateIndex).state_id), ...
            'fieldfox:link','Trace uses an inconsistent state at a part boundary.');
        power = zeros(rows,slots,points,'single');
        power(:,1,:) = reshape(data.power_dbm,rows,1,points);
        data = rmfield(data,{'power_dbm','trace_slot','effective_step'});
        for slot = 1:slots-1
            selected = read_fieldfox(source,'StartSweep',first,'StopSweep',stop, ...
                'TraceSlot',slot,args{:});
            assert(isequal(selected.timestamp_ticks,data.timestamp_ticks) && ...
                isequal(selected.state_ids,data.state_ids), ...
                'fieldfox:changed','Session changed while exporting.');
            power(:,slot+1,:) = reshape(selected.power_dbm,rows,1,points);
        end
        clear selected
        data.power_dbm_traces = power; clear power
        data.trace_slot_indices = int32((0:slots-1)');
        data.elapsed_s = nan(rows,1);
        if probe.timestamp_ticks(1)>0
            valid=data.timestamp_ticks>0;
            data.elapsed_s(valid)=double(data.timestamp_ticks(valid)-probe.timestamp_ticks(1))/1e7;
        end
        data.state_id = states(stateIndex).state_id;
        data.axis_kind = 'frequency_hz';
        if isempty(data.frequency_hz), data.axis_kind = 'time_axis_s'; end
        partNumber = partNumber+1; filename = sprintf('part_%06d.mat',partNumber);
        save(fullfile(stage,filename),'-struct','data','-v7.3');
        part = struct('file',filename,'state_id',data.state_id,'start_sweep',first, ...
            'stop_sweep',stop,'n_sweeps',rows,'axis_kind',data.axis_kind);
        manifest.parts{end+1} = part;
        clear data
        fprintf('Exported %d / %d sweeps (%s)\n',stop,total,filename);
    end
end
[fid,msg] = fopen(fullfile(stage,'manifest.json'),'w','n','UTF-8');
assert(fid>=0,'fieldfox:io',msg); fileCleanup = onCleanup(@() fclose(fid));
fprintf(fid,'%s\n',jsonencode(manifest,PrettyPrint=true)); clear fileCleanup
assert(~isfolder(target) && ~isfile(target),'fieldfox:output','Output already exists.');
[ok,msg] = movefile(stage,target); assert(ok,'fieldfox:io',msg);
clear cleanup
fprintf('Complete: %d MAT parts in %s\n',partNumber,target);
end

function remove_stage(stage)
% This is only our unique, previously checked temporary folder.
if isfolder(stage), rmdir(stage,'s'); end
end
