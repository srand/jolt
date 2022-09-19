#include <boost/json.hpp>
#include <iostream>

using namespace boost::json;

int main() {
    object obj;
    obj[ "name" ] = "Hello world";
    std::cout << obj["name"] << "\n";
    return 0;
}