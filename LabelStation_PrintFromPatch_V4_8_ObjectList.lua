local pluginName = select(1, ...)

-- Label Station Print From Patch V4.8 ObjectList
--
-- Uses the now-proven ObjectList fixture handle properties:
--   h.patch / h.PATCH / h.Patch           -> universe.address, e.g. 21.361
--   h.NO / h.FID / h.INDEX               -> fixture ID
--   h.FIXTURE / h.name                   -> fixture/profile name
--   h.MODE                               -> mode/profile text, parsed into label Profile + Description
--
-- V4.7 change: Profile is now the MA mode number/text, NOT the DMX footprint.
-- Examples:
--   140 140:D16 CCT GM C RGB S        -> Profile: Mode 140 / Description: D16 CCT GM C RGB S
--   38 Mode 25 - LE CCT+RGBW 16Bit    -> Profile: Mode 25 / Description: LE CCT+RGBW 16Bit
--   3 Standard                        -> Profile: Mode 3 / Description: Standard
--
-- This version avoids Patch().Stages fixture-row patch parsing entirely because those
-- rows did not reliably expose printable patch addresses in your showfile.

local DEFAULT_RANGE = "1 thru"
local DEFAULT_SERVER = "127.0.0.1:5000"
local LAST_SERVER_VAR = "LabelStationLastServer"
local OPEN_THRU_MAX = 9999

local function log(msg)
    Printf("[LabelStation] " .. tostring(msg))
end

local function json_escape(s)
    s = tostring(s or "")
    s = s:gsub("\\", "\\\\")
    s = s:gsub('"', '\\"')
    s = s:gsub("\r", "\\r")
    s = s:gsub("\n", "\\n")
    s = s:gsub("\t", "\\t")
    return s
end

local function trim(s)
    s = tostring(s or "")
    return s:gsub("^%s+", ""):gsub("%s+$", "")
end

local function lower(s)
    return string.lower(tostring(s or ""))
end

local function strip_http_prefix(s)
    s = tostring(s or "")
    s = s:gsub("^http://", "")
    s = s:gsub("^https://", "")
    s = s:gsub("/.*$", "")
    return s
end

local function split_host_port(target)
    target = strip_http_prefix(target)
    target = trim(target)

    local host, port = target:match("^([^:]+):(%d+)$")
    if not host then
        host = target
        port = "5000"
    end

    return host, tonumber(port)
end

local function get_user_var(name, fallback)
    local ok, value = pcall(function()
        return GetVar(UserVars(), name)
    end)
    if ok and value ~= nil and tostring(value) ~= "" then
        return tostring(value)
    end
    return fallback
end

local function set_user_var(name, value)
    Cmd('SetUserVariable "' .. name .. '" "' .. tostring(value or "") .. '"')
end

local function raw_http_post(host, port, path, body)
    local socket = require("socket")

    local tcp, err = socket.tcp()
    if not tcp then
        return false, "socket.tcp() failed: " .. tostring(err)
    end

    tcp:settimeout(8)

    local ok, connect_err = tcp:connect(host, port)
    if not ok then
        tcp:close()
        return false, "connect failed: " .. tostring(connect_err)
    end

    local request =
        "POST " .. path .. " HTTP/1.1\r\n" ..
        "Host: " .. host .. ":" .. tostring(port) .. "\r\n" ..
        "User-Agent: grandMA3-LabelStation-PrintV4.8\r\n" ..
        "Content-Type: application/json\r\n" ..
        "Content-Length: " .. tostring(#body) .. "\r\n" ..
        "Connection: close\r\n" ..
        "\r\n" ..
        body

    local sent, send_err = tcp:send(request)
    if not sent then
        tcp:close()
        return false, "send failed: " .. tostring(send_err)
    end

    local response, recv_err, partial = tcp:receive("*a")
    tcp:close()

    response = response or partial or ""
    if response == "" then
        return false, "empty response: " .. tostring(recv_err)
    end

    local status = response:match("HTTP/%d%.%d%s+(%d+)")
    if status ~= "200" then
        return false, "HTTP status " .. tostring(status) .. ": " .. response:sub(1, 1500)
    end

    return true, response
end

local function safe_field(handle, field)
    local ok, value = pcall(function()
        return handle[field]
    end)
    if ok and value ~= nil then
        return tostring(value)
    end
    return ""
end

local function first_nonempty(handle, fields)
    for _, f in ipairs(fields) do
        local v = trim(safe_field(handle, f))
        if v ~= "" and v ~= "nil" and v ~= "None" and v ~= "<invalid>" then
            return v
        end
    end
    return ""
end

local function parse_patch(patch)
    patch = trim(patch)

    local u, a = patch:match("^(%d+)%.(%d+)$")
    if not u then
        u, a = patch:match("^(%d+)/(%d+)$")
    end

    if not u then
        return nil, nil
    end

    return tonumber(u), tonumber(a)
end

local function normalize_range_for_objectlist(range)
    local s = tostring(range or "")
    s = s:gsub("^%s*[Ff]ixture%s+", "")
    s = s:gsub("%s+", " ")
    s = trim(s)

    if s == "" then
        s = DEFAULT_RANGE
    end

    -- Shortcut syntax: allow "201 t 203" and "201 t" as a fast keypad form.
    -- Normalize those to MA's "thru" before giving the string to ObjectList.
    s = s:gsub("(%d+)%s+[Tt]%s+(%d+)", "%1 thru %2")
    s = s:gsub("(%d+)%s+[Tt]%s*$", "%1 thru")

    -- Also tolerate "through".
    s = s:gsub("(%d+)%s+[Tt][Hh][Rr][Oo][Uu][Gg][Hh]%s+(%d+)", "%1 thru %2")
    s = s:gsub("(%d+)%s+[Tt][Hh][Rr][Oo][Uu][Gg][Hh]%s*$", "%1 thru")

    -- MA's ObjectList does not reliably accept open-ended "1 thru" in plugin strings.
    -- Translate it to a high finite range. ObjectList should only return existing fixtures.
    s = s:gsub("(%d+)%s+[Tt][Hh][Rr][Uu]%s*$", "%1 thru " .. tostring(OPEN_THRU_MAX))

    return s
end

local function clean_numeric(s)
    s = trim(s)
    local n = s:match("(%d+)")
    return n
end

local function parse_mode_for_label(mode_raw)
    local m = trim(mode_raw)
    if m == "" or m == "nil" or m == "None" or m == "<invalid>" then
        return "", ""
    end

    -- MA often prefixes the visible mode with an internal row/object number.
    -- Examples:
    --   140 140:D16 CCT GM C RGB S
    --   38 Mode 25 - LE CCT+RGBW 16Bit
    --   4 MODE120: CCT+RGB 16bit +motor+CONTROL_IAN#2
    --   3 Standard
    -- Remove ONLY the first leading number+space before parsing the actual mode.
    local body = m:match("^%s*%d+%s+(.+)$") or m
    body = trim(body)

    local n, desc

    -- MODE120: Something / Mode 25: Something / Mode 25 - Something
    n, desc = body:match("^[Mm][Oo][Dd][Ee]%s*(%d+)%s*[:%-]%s*(.+)$")
    if n then
        return "Mode " .. tostring(n), trim(desc)
    end

    -- 140:D16 CCT GM C RGB S
    n, desc = body:match("^(%d+)%s*:%s*(.+)$")
    if n then
        return "Mode " .. tostring(n), trim(desc)
    end

    -- 3 Standard
    n, desc = body:match("^(%d+)%s+(.+)$")
    if n then
        return "Mode " .. tostring(n), trim(desc)
    end

    -- Standard-like value with no visible number. Use it as the description and
    -- leave profile blank so the website override screen can handle it if needed.
    return "", body
end

local function handle_to_fixture(handle)
    local fid = first_nonempty(handle, {"NO", "no", "FID", "fid", "INDEX", "index", "Number", "number"})
    fid = clean_numeric(fid)

    if fid == nil or fid == "0" then
        return nil, "no_fid"
    end

    local patch = first_nonempty(handle, {"patch", "PATCH", "Patch"})
    local universe, address = parse_patch(patch)
    if universe == nil or address == nil then
        return nil, "bad_patch:" .. tostring(patch)
    end

    local fixturetype = first_nonempty(handle, {"FIXTURE", "fixture", "Fixture", "name", "NAME", "Name"})
    if fixturetype == "" then
        fixturetype = "Fixture"
    end

    if lower(fixturetype) == "grouping" then
        return nil, "grouping"
    end

    local mode_raw = first_nonempty(handle, {"MODE", "Mode", "mode"})
    local profile, description = parse_mode_for_label(mode_raw)

    return {
        fid = tostring(fid),
        universe = universe,
        address = address,
        fixturetype = fixturetype,
        profile = profile,
        description = description,
        raw_mode = mode_raw,
        raw_patch = patch
    }, nil
end

local function fixture_to_json(fx)
    return
        "{" ..
        '"fid":"' .. json_escape(fx.fid) .. '",' ..
        '"universe":' .. tostring(fx.universe) .. "," ..
        '"address":' .. tostring(fx.address) .. "," ..
        '"profile":"' .. json_escape(fx.profile or "") .. '",' ..
        '"description":"' .. json_escape(fx.description or "") .. '",' ..
        '"fixturetype":"' .. json_escape(fx.fixturetype or "") .. '",' ..
        '"raw_mode":"' .. json_escape(fx.raw_mode or "") .. '",' ..
        '"raw_patch":"' .. json_escape(fx.raw_patch or "") .. '"' ..
        "}"
end

local function collect_from_objectlist(range)
    local normalized_range = normalize_range_for_objectlist(range)
    local selection_string = "Fixture " .. normalized_range

    log("ObjectList: " .. selection_string)

    local ok, objects = pcall(function()
        return ObjectList(selection_string)
    end)

    if not ok or objects == nil then
        return {}, {
            selection = selection_string,
            handles = 0,
            printable = 0,
            grouping = 0,
            bad_patch = 0,
            no_fid = 0
        }
    end

    local fixtures = {}
    local stats = {
        selection = selection_string,
        handles = 0,
        printable = 0,
        grouping = 0,
        bad_patch = 0,
        no_fid = 0,
        other_skip = 0
    }

    local seen = {}

    for _, h in pairs(objects) do
        stats.handles = stats.handles + 1
        local fx, reason = handle_to_fixture(h)

        if fx ~= nil then
            if not seen[fx.fid] then
                seen[fx.fid] = true
                table.insert(fixtures, fx)
                stats.printable = stats.printable + 1

                if stats.printable <= 30 then
                    log("Prepared Fixture " .. fx.fid .. " " .. fx.fixturetype .. " @ " .. fx.raw_patch ..
                        " / " .. tostring(fx.profile) .. " / " .. tostring(fx.description))
                elseif stats.printable == 31 then
                    log("More than 30 printable fixtures found; suppressing per-fixture log.")
                end
            end
        else
            if reason == "grouping" then
                stats.grouping = stats.grouping + 1
            elseif reason == "no_fid" then
                stats.no_fid = stats.no_fid + 1
            elseif tostring(reason):find("bad_patch", 1, true) then
                stats.bad_patch = stats.bad_patch + 1
            else
                stats.other_skip = stats.other_skip + 1
            end
        end
    end

    table.sort(fixtures, function(a, b)
        return tonumber(a.fid) < tonumber(b.fid)
    end)

    return fixtures, stats
end

local function show_ui()
    local last_server = get_user_var(LAST_SERVER_VAR, DEFAULT_SERVER)

    local ok, result = pcall(function()
        return MessageBox({
            title = "Label Station Print",
            message = "Send MA patch fixtures to the laptop label server.",
            commands = {
                {value = 1, name = "Print"},
                {value = 0, name = "Cancel"}
            },
            inputs = {
                {name = "range", value = DEFAULT_RANGE, whiteFilter = "0123456789tThHrRuUoOgG +fixtureFIXTURE"},
                {name = "server", value = last_server, whiteFilter = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.:/-_"}
            }
        })
    end)

    if ok and result ~= nil then
        local command_value = result.result or result.success or result.command
        if command_value == 0 or command_value == false then
            return nil, nil, "Cancelled"
        end

        local inputs = result.inputs or {}
        local range = nil
        local server = nil

        if inputs.range ~= nil then range = tostring(inputs.range) end
        if inputs.server ~= nil then server = tostring(inputs.server) end

        if range == nil or server == nil then
            for _, item in pairs(inputs) do
                if type(item) == "table" then
                    if item.name == "range" then range = tostring(item.value or "") end
                    if item.name == "server" then server = tostring(item.value or "") end
                end
            end
        end

        if range ~= nil and server ~= nil then
            range = trim(range)
            server = trim(server)
            if range == "" then range = DEFAULT_RANGE end
            if server == "" then server = last_server end
            return range, server, nil
        end
    end

    local range = TextInput("Fixture range to print", DEFAULT_RANGE)
    if range == nil or range == "" then
        return nil, nil, "Cancelled"
    end

    local server = TextInput("Label Station server IP:port", last_server)
    if server == nil or server == "" then
        return nil, nil, "Cancelled"
    end

    return trim(range), trim(server), nil
end

function Main(display_handle, args)
    log("Patch-to-print v4.8 ObjectList starting")

    local range, target, ui_err = show_ui()
    if ui_err then
        log(ui_err)
        return
    end

    local host, port = split_host_port(target)
    if host == nil or host == "" or port == nil then
        ErrPrintf("[LabelStation] Invalid server: " .. tostring(target))
        return
    end

    set_user_var(LAST_SERVER_VAR, target)
    Cmd("ChangeDestination Root")

    local fixtures, stats = collect_from_objectlist(range)

    log("ObjectList handles: " .. tostring(stats.handles) ..
        ", printable: " .. tostring(stats.printable))
    log("Skipped grouping: " .. tostring(stats.grouping) ..
        ", no FID: " .. tostring(stats.no_fid) ..
        ", bad/unpatched patch: " .. tostring(stats.bad_patch) ..
        ", other: " .. tostring(stats.other_skip or 0))

    if #fixtures == 0 then
        ErrPrintf("[LabelStation] No printable fixtures found in range: " .. tostring(range))
        return
    end

    local fixture_bits = {}
    for _, fx in ipairs(fixtures) do
        table.insert(fixture_bits, fixture_to_json(fx))
    end

    local body =
        "{" ..
        '"source":"grandMA3",' ..
        '"plugin":"LabelStation_PrintFromPatch_V4_8_ObjectList",' ..
        '"range":"' .. json_escape(range) .. '",' ..
        '"objectlist_selection":"' .. json_escape(stats.selection or "") .. '",' ..
        '"fixture_count":' .. tostring(#fixtures) .. "," ..
        '"skipped_grouping":' .. tostring(stats.grouping) .. "," ..
        '"skipped_no_fid":' .. tostring(stats.no_fid) .. "," ..
        '"skipped_bad_patch":' .. tostring(stats.bad_patch) .. "," ..
        '"fixtures":[' .. table.concat(fixture_bits, ",") .. "]" ..
        "}"

    log("POST " .. tostring(#fixtures) .. " fixtures to http://" .. host .. ":" .. tostring(port) .. "/print")

    local ok, result = raw_http_post(host, port, "/print", body)
    if ok then
        log("SUCCESS: Label Station accepted print job")
        log("Response: " .. result:sub(1, 700))
    else
        ErrPrintf("[LabelStation] FAILED: " .. tostring(result))
    end
end

return Main
