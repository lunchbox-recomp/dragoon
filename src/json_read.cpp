// See json_read.h.
#include "json_read.h"
#include <cstdint>
#include <cstdlib>

namespace dragoon {

const Json* Json::get(const std::string& key) const {
    if (type != Type::object) return nullptr;
    for (const auto& member : object)
        if (member.first == key) return &member.second;
    return nullptr;
}

namespace {

bool is_digit(char c) { return c >= '0' && c <= '9'; }

void put_utf8(uint32_t c, std::string& out) {
    if (c < 0x80) {
        out += (char)c;
    } else if (c < 0x800) {
        out += (char)(0xC0 | (c >> 6));
        out += (char)(0x80 | (c & 0x3F));
    } else if (c < 0x10000) {
        out += (char)(0xE0 | (c >> 12));
        out += (char)(0x80 | ((c >> 6) & 0x3F));
        out += (char)(0x80 | (c & 0x3F));
    } else {
        out += (char)(0xF0 | (c >> 18));
        out += (char)(0x80 | ((c >> 12) & 0x3F));
        out += (char)(0x80 | ((c >> 6) & 0x3F));
        out += (char)(0x80 | (c & 0x3F));
    }
}

class Reader {
public:
    explicit Reader(const std::string& text) : s_(text) {}

    bool document(Json& out) {
        space();
        if (!value(out, 0)) return false;
        space();
        return i_ == s_.size();
    }

private:
    const std::string& s_;
    size_t i_ = 0;

    bool at(char c) const { return i_ < s_.size() && s_[i_] == c; }
    bool take(char c) {
        if (!at(c)) return false;
        i_++;
        return true;
    }
    void space() {
        while (at(' ') || at('\t') || at('\n') || at('\r')) i_++;
    }
    bool word(const char* w) {
        for (; *w; w++)
            if (!take(*w)) return false;
        return true;
    }

    bool value(Json& out, int depth) {
        if (at('{') || at('[')) {
            if (depth >= kJsonMaxDepth) return false;
            return at('{') ? object(out, depth + 1) : array(out, depth + 1);
        }
        if (at('"')) {
            out.type = Json::Type::string;
            return string(out.string);
        }
        if (at('t') || at('f')) {
            out.type = Json::Type::boolean;
            out.boolean = at('t');
            return word(out.boolean ? "true" : "false");
        }
        if (at('n')) {
            out.type = Json::Type::null;
            return word("null");
        }
        out.type = Json::Type::number;
        return number(out.number);
    }

    bool object(Json& out, int depth) {
        out.type = Json::Type::object;
        take('{');
        space();
        if (take('}')) return true;
        for (;;) {
            std::pair<std::string, Json> member;
            if (!at('"') || !string(member.first)) return false;
            space();
            if (!take(':')) return false;
            space();
            if (!value(member.second, depth)) return false;
            out.object.push_back(std::move(member));
            space();
            if (take('}')) return true;
            if (!take(',')) return false;
            space();
        }
    }

    bool array(Json& out, int depth) {
        out.type = Json::Type::array;
        take('[');
        space();
        if (take(']')) return true;
        for (;;) {
            Json item;
            if (!value(item, depth)) return false;
            out.array.push_back(std::move(item));
            space();
            if (take(']')) return true;
            if (!take(',')) return false;
            space();
        }
    }

    // -? (0 | [1-9][0-9]*) (. [0-9]+)? ([eE] [+-]? [0-9]+)?, checked before strtod reads it.
    bool number(double& out) {
        const size_t start = i_;
        take('-');
        // A 0 stands alone, so a digit after it is left over and the read fails.
        if (!take('0') && !digits()) return false;
        if (take('.') && !digits()) return false;
        if (take('e') || take('E')) {
            if (!take('+')) take('-');
            if (!digits()) return false;
        }
        out = strtod(s_.substr(start, i_ - start).c_str(), nullptr);
        return true;
    }

    bool digits() {
        const size_t start = i_;
        while (i_ < s_.size() && is_digit(s_[i_])) i_++;
        return i_ > start;
    }

    bool hex4(uint32_t& out) {
        if (s_.size() - i_ < 4) return false;
        out = 0;
        for (int n = 0; n < 4; n++) {
            const char c = s_[i_++];
            uint32_t v;
            if (is_digit(c)) v = (uint32_t)(c - '0');
            else if (c >= 'a' && c <= 'f') v = (uint32_t)(c - 'a' + 10);
            else if (c >= 'A' && c <= 'F') v = (uint32_t)(c - 'A' + 10);
            else return false;
            out = out << 4 | v;
        }
        return true;
    }

    // A \u escape, or a pair of them for a character past U+FFFF. A NUL is refused, since it
    // would cut the string short wherever it's used as a C string.
    bool code_point(std::string& out) {
        uint32_t c;
        if (!hex4(c) || c == 0 || (c >= 0xDC00 && c <= 0xDFFF)) return false;
        if (c >= 0xD800 && c <= 0xDBFF) {
            uint32_t low;
            if (!take('\\') || !take('u') || !hex4(low) || low < 0xDC00 || low > 0xDFFF) return false;
            c = 0x10000 + ((c - 0xD800) << 10) + (low - 0xDC00);
        }
        put_utf8(c, out);
        return true;
    }

    bool string(std::string& out) {
        take('"');
        for (;;) {
            if (i_ >= s_.size()) return false;
            const char c = s_[i_++];
            if (c == '"') return true;
            if ((unsigned char)c < 0x20) return false;
            if (c != '\\') {
                out += c;
                continue;
            }
            if (i_ >= s_.size()) return false;
            switch (s_[i_++]) {
            case '"': out += '"'; break;
            case '\\': out += '\\'; break;
            case '/': out += '/'; break;
            case 'b': out += '\b'; break;
            case 'f': out += '\f'; break;
            case 'n': out += '\n'; break;
            case 'r': out += '\r'; break;
            case 't': out += '\t'; break;
            case 'u':
                if (!code_point(out)) return false;
                break;
            default: return false;
            }
        }
    }
};

}  // namespace

bool json_read(const std::string& text, Json& out) {
    out = Json();
    return Reader(text).document(out);
}

}  // namespace dragoon
