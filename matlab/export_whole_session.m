% Edit these paths, then press Run. No Python or Data Link is required.
addpath(fileparts(mfilename('fullpath')));
sessionFolder = 'D:\data\RTAUTOsession01';
outputFolder = 'D:\exports\RTAUTOsession01_MAT'; % Must be a NEW folder.
sweepsPerPart = 5000;

export_fieldfox_session(sessionFolder, outputFolder, ...
    'SweepsPerPart', sweepsPerPart, 'SourceTimeZone', 'EST');
% EST means fixed UTC-05:00. UTC and EST times are both saved.
% Output: part_000001.mat, part_000002.mat, ... and manifest.json.
