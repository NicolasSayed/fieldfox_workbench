function [counts, starts, recovery] = fieldfox_trace_layout(folder, files, stride, version, recover, expected, states)
% Infer short partition tails from RPX counts or the next file's first ID.
% FDAT/fDEV layout: Utility.dll ano/ann.qx and apf.t cases 11/15/5.
sizes = [files.bytes]; counts = sizes/stride; starts = [0 cumsum(counts(1:end-1))];
recovery = struct('enabled',logical(recover),'zero_filled_sweeps',0,'partitions',{{}});
recovery.power_fill_dbm = -300; recovery.auxiliary_fill_value = 0;
recovery.ignored_trailing_bytes = 0;
if ~recover
    assert(isempty(expected),'fieldfox:recovery','ExpectedSweeps requires RecoverIncomplete.');
    assert(all(counts>0 & counts==fix(counts)),'fieldfox:truncated','Invalid TRC file length.');
    return
end
if ~isempty(expected), validateattributes(expected,{'numeric'},{'scalar','positive','integer','finite'}); end
store = struct; listing = dir(folder);
for entry = listing'
    if ~entry.isdir && any(strcmpi(entry.name,{'STA.rpx','TRC.rpx'}))
        part = index_store(fullfile(folder,entry.name));
        if ~isempty(fieldnames(part))
            if ~isempty(fieldnames(store)), assert(isequal(store,part),'fieldfox:index','Conflicting RPX TRC counts.'); end
            store = part;
        end
    end
end
if ~isempty(fieldnames(store))
    assert(isfield(store,'total') && isfield(store,'nominal') && store.total>0 && store.nominal>0, ...
        'fieldfox:index','Invalid RPX TRC counts.');
    n = ceil(store.total/store.nominal);
    assert(n<=numel(files),'fieldfox:index','RPX describes missing TRC partitions.');
    counts = min(store.nominal,store.total-(0:n-1)*store.nominal);
    if isfield(store,'deviations')
        for pair = store.deviations'
            index = pair(1)+1; value = pair(2);
            assert(index>=1 && index<=numel(files) && value>=0,'fieldfox:index','Invalid RPX file deviation.');
            counts(end+1:index) = store.nominal;
            counts(index) = value;
        end
    end
    assert(numel(counts)==numel(files) && sum(counts)==store.total,'fieldfox:index','Inconsistent RPX file/total counts.');
    assert(isempty(expected) || expected==store.total,'fieldfox:index','ExpectedSweeps conflicts with RPX.');
    starts = [0 cumsum(counts(1:end-1))]; source = 'RPX FDAT/fDEV counts';
else
    starts = zeros(1,numel(files));
    for k = 1:numel(files)
        first = 0;
        if k>1, first=starts(k-1)+ceil(sizes(k-1)/stride); end
        if sizes(k)>=8
            [fid,msg] = fopen(files(k).path,'rb'); assert(fid>=0,'fieldfox:io',msg);
            headerBytes = 32+12*(version>=4);
            cleanup = onCleanup(@() fclose(fid)); b = fread(fid,min(headerBytes,sizes(k)),'*uint8'); clear cleanup
            if version>=5, actual=double(number(b,5,'int32')); else, actual=double(number(b,1,'uint16')); end
            identical=false;
            if k>1 && actual==starts(k-1)
                identical=sizes(k-1)<headerBytes || same_prefix(files(k-1).path,files(k).path,sizes(k-1));
            end
            assert((k~=1 || actual==0) && (k==1 || actual>starts(k-1) || identical), ...
                'fieldfox:link','Invalid first trace ID: partition starts must increase.');
            if numel(b)==headerBytes
                sid=double(number(b,3,'uint16'));
                expectedState=find([states.first_trace]<=actual,1,'last')-1;
                assert(sid<numel(states) && sid==expectedState,'fieldfox:link','Invalid first trace state link.');
                ticks=number(b,9,'int64'); parameter=number(b,headerBytes-7,'double');
                maximum=int64(315537897599)*int64(10000000)+int64(9999999);
                assert(ticks>0 && ticks<=maximum && isfinite(parameter) && parameter>=-2, ...
                    'fieldfox:header','Invalid first trace header.');
            else
                assert(actual>=first,'fieldfox:link','Incomplete first header cannot establish an overlapping boundary.');
            end
            first = actual;
        end
        starts(k) = first;
    end
    last = starts(end)+ceil(sizes(end)/stride);
    if ~isempty(expected)
        assert(expected>=last,'fieldfox:recovery','ExpectedSweeps is smaller than available data.'); last=expected;
    end
    counts = diff([starts last]); source = 'partition first sweep IDs / physical tail / optional ExpectedSweeps';
end
assert(sum(counts)>0,'fieldfox:recovery','Empty session: provide ExpectedSweeps.');
recovery.count_source = source;
recovery.note = 'Missing power uses -300 dBm placeholders. Missing headers have ticks=0 and blank times. zero_filled is the legacy recovery flag name.';
for k = 1:numel(files)
    usable=min(sizes(k),counts(k)*stride);
    complete = floor(usable/stride); missing = counts(k)-complete;
    ignored=sizes(k)-usable;
    if missing>0 || ignored>0
        recovery.zero_filled_sweeps = recovery.zero_filled_sweeps+missing;
        recovery.ignored_trailing_bytes = recovery.ignored_trailing_bytes+ignored;
        recovery.partitions{end+1} = struct('file',files(k).path,'start_sweep',starts(k), ...
            'expected_sweeps',counts(k),'complete_sweeps',complete, ...
            'partial_bytes',mod(usable,stride),'zero_filled_sweeps',missing,'ignored_trailing_bytes',ignored);
    end
end
end

function same = same_prefix(first,second,remaining)
[left,msg]=fopen(first,'rb'); assert(left>=0,'fieldfox:io',msg); closeLeft=onCleanup(@() fclose(left));
[right,msg]=fopen(second,'rb'); assert(right>=0,'fieldfox:io',msg); closeRight=onCleanup(@() fclose(right));
same=true;
while remaining>0
    n=min(65536,remaining); a=fread(left,n,'*uint8'); b=fread(right,n,'*uint8');
    if numel(a)~=n || ~isequal(a,b), same=false; return; end
    remaining=remaining-n;
end
end

function store = index_store(path)
% Read bounded RPX chunks and verify CRC; never deserialize vendor objects.
[fid,msg] = fopen(path,'rb'); assert(fid>=0,'fieldfox:io',msg); cleanup = onCleanup(@() fclose(fid));
header = fread(fid,10,'*uint8'); store = struct;
assert(numel(header)==10 && strcmp(char(header(1:8)'),'FFRPINDX') && number(header,9,'uint16')==1, ...
    'fieldfox:index','Unsupported RPX header.');
while true
    b = fread(fid,8,'*uint8'); if isempty(b), break; end
    assert(numel(b)==8,'fieldfox:index','Truncated RPX chunk header.');
    n = double(number(b,1,'int32')); tag = b(5:8);
    assert(n>=0 && n<=64*1024^2,'fieldfox:index','Invalid RPX chunk size.');
    body = fread(fid,n,'*uint8'); crc = fread(fid,4,'*uint8');
    assert(numel(body)==n && numel(crc)==4,'fieldfox:index','Truncated RPX chunk.');
    checksum = java.util.zip.CRC32;
    checksum.update(typecast([tag;body],'int8'));
    assert(uint32(checksum.getValue())==number(crc,1,'uint32'),'fieldfox:index','RPX CRC mismatch.');
    name = char(tag'); if ~any(strcmp(name,{'FDAT','fDEV'})), continue; end
    fields = struct; kind = ''; pos = 1;
    while pos<=n
        assert(pos+4<=n,'fieldfox:index','Truncated RPX item.');
        length = double(number(body,pos,'int32')); id = body(pos+4); pos=pos+5;
        assert(length>=0 && length<=n-pos+1,'fieldfox:index','Invalid RPX item size.');
        raw = body(pos:pos+length-1); pos=pos+length;
        if id==10, kind=char(raw');
        elseif strcmp(name,'FDAT') && any(id==[11 13])
            assert(length==4,'fieldfox:index','Invalid RPX count size.');
            if id==11, fields.total=double(number(raw,1,'int32')); else, fields.nominal=double(number(raw,1,'int32')); end
        elseif strcmp(name,'fDEV') && id==12
            assert(mod(length,8)==0,'fieldfox:index','Invalid RPX deviation size.');
            fields.deviations = reshape(double(number(raw,1,'int32',length/4)),2,[])';
        end
    end
    if strcmp(kind,'TRC')
        keys=fieldnames(fields);
        for j=1:numel(keys), store.(keys{j})=fields.(keys{j}); end
    end
end
end

function v = number(b,start,kind,count)
if nargin<4, count=1; end
width=numel(typecast(cast(0,kind),'uint8')); v=typecast(b(start:start+count*width-1),kind);
[~,~,endian]=computer; if endian=='B', v=swapbytes(v); end
end
