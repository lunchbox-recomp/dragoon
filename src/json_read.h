// JSON text read into a tree, for what the repository's Python tools print. It takes RFC 8259's
// grammar, which Python's json.dumps writes, with \u escapes turned into UTF-8. A string holding
// \u0000 is refused.
#pragma once
#include <string>
#include <utility>
#include <vector>

namespace dragoon {

struct Json {
    enum class Type { null, boolean, number, string, array, object };
    Type type = Type::null;
    bool boolean = false;
    double number = 0;
    std::string string;
    std::vector<Json> array;
    std::vector<std::pair<std::string, Json>> object;  // in the text's order

    // The member named `key`, or null when this isn't an object or has no such member.
    const Json* get(const std::string& key) const;
};

// Nesting deeper than this is refused, so a read can't run out of stack.
constexpr int kJsonMaxDepth = 32;

// The one value `text` holds, with white space allowed around it. False for anything else,
// and `out` is then unspecified.
bool json_read(const std::string& text, Json& out);

}  // namespace dragoon
